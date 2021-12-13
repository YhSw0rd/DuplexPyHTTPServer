import http.server
import os
from http import HTTPStatus
import urllib.parse
import html
import io
import sys
from functools import partial
import contextlib
import socket
import re
import json
from rich.progress import Progress



class ConsoleProgressSingleton(object):
    __instance=None
    __progress = None
    
    def __new__(cls, *args, **kwargs):
        if ConsoleProgressSingleton.__instance is None:
            ConsoleProgressSingleton.__instance=object.__new__(cls,*args, **kwargs)
        return ConsoleProgressSingleton.__instance
    
    def __enter__(self):
        if self.__progress == None:
            self.__progress = Progress()
            self.__progress.start()
        return self.__progress

    def __exit__(self,*args):
        if self.__progress.finished:
            self.__progress.stop()
            self.__progress = None

class DuplexHTTPRequestHandler(http.server.SimpleHTTPRequestHandler):
    
    def list_directory(self, path):
        try:
            list = os.listdir(path)
        except OSError:
            self.send_error(
                HTTPStatus.NOT_FOUND,
                "No permission to list directory")
            return None
        list.sort(key=lambda a: a.lower())
        r = []
        try:
            displaypath = urllib.parse.unquote(self.path,
                                               errors='surrogatepass')
        except UnicodeDecodeError:
            displaypath = urllib.parse.unquote(path)
        displaypath = html.escape(displaypath, quote=False)
        enc = sys.getfilesystemencoding()
        title = 'Directory listing for %s' % displaypath
        r.append('<!DOCTYPE HTML PUBLIC "-//W3C//DTD HTML 4.01//EN" '
                 '"http://www.w3.org/TR/html4/strict.dtd">')
        r.append('<html>\n<head>')
        r.append('<meta http-equiv="Content-Type" '
                 'content="text/html; charset=%s">' % enc)
        r.append('<title>%s</title>\n</head>' % title)
        r.append('<body>\n<h1>%s</h1>' % title)
        r.append('<hr>\n<ul>')
        for name in list:
            fullname = os.path.join(path, name)
            displayname = linkname = name
            if os.path.isdir(fullname):
                displayname = name + "/"
                linkname = name + "/"
            if os.path.islink(fullname):
                displayname = name + "@"
            r.append('<li><a href="%s">%s</a></li>'
                    % (urllib.parse.quote(linkname,
                                          errors='surrogatepass'),
                       html.escape(displayname, quote=False)))
        r.append('''</ul>\n<hr>\n
        <div id="progress-bar" style="position: absolute;bottom: 0;left: 0;">
            
        </div>
        
        </body>\n''')
        # 此处追加js
        r.append('''
            <script>
                document.addEventListener("drop",preventDe);
                document.addEventListener("dragleave",preventDe);
                document.addEventListener("dragover",preventDe);
                document.addEventListener("dragenter",preventDe);
                function preventDe(e){
                    e.preventDefault();
                }
                var fileList = [];
                document.addEventListener("drop",function(e){
                    e.preventDefault();
                    let dropFiles = [...e.dataTransfer.files];
                    dropFiles.forEach(function(file,index,array){
                        fileList.push(file);
                        var data = new FormData();
                        data.append("", file);
                        var xhr = new XMLHttpRequest();
                        xhr.withCredentials = true;
                        var progressBar = document.getElementById("progress-bar");
                        var childDiv = document.createElement('div');
                        progressBar.appendChild(childDiv);
                        xhr.addEventListener("readystatechange", function() {
                            if(this.readyState === 4) {
                                console.log(this.responseText);
                                fileList.splice(fileList.indexOf(file),1)
                                if(fileList.length == 0){
                                    window.location.reload();
                                }
                            }
                        });
                        xhr.upload.addEventListener("progress", function(evt){
                            if (evt.lengthComputable) {
                                var percentComplete = Math.round(evt.loaded * 100 / evt.total);
                                if( percentComplete == 100){
                                    progressBar.removeChild(childDiv);
                                }else{
                                    childDiv.innerHTML=file.name + '...'+percentComplete+"%";
                                }
                            }
                        }, false);
                        xhr.open("POST", window.location.href);
                        xhr.send(data);
                    });
                });
            </script>
        ''')
        r.append('</html>\n')
        encoded = '\n'.join(r).encode(enc, 'surrogateescape')
        f = io.BytesIO()
        f.write(encoded)
        f.seek(0)
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-type", "text/html; charset=%s" % enc)
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        return f

    def do_POST(self):
        # 报文体总长度（字节长度）
        content_length = int(self.headers['Content-Length'])
        chunk = 2**10
        # 如果有报文体长度
        # progress = Progress()
        
        
        try:
            if content_length > 0 :
                # 取得第一行boundry，这一行没用，结尾还有一个boundry但是多了两个“-”，所以再加2，再减去2是因为文件结尾和boundry之间有'\r\n'占俩字节
                boundry = self.rfile.readline(chunk)
                content_length -= ( len(boundry)*2 + 2 + 2 )
                with ConsoleProgressSingleton() as progress:
                    # 第二行有文件名
                    filename = self.rfile.readline(chunk)
                    content_length -= len(filename)
                    file_name = re.findall('.*filename="(.*)".*',filename.decode('utf-8'))
                    
                    # 获取到文件名才能真正开始
                    if file_name and len(file_name) > 0:
                        file_name = file_name[0]
                    else:
                        # 如果没有文件名先不管
                        pass
                    
                    # print(file_name)
                    # 再去掉两行没用的
                    content_length -= len(self.rfile.readline(chunk))
                    content_length -= len(self.rfile.readline(chunk))
                    upload_task =  progress.add_task("[red]Uploading %s..."%file_name, total=content_length)
                    # 创建文件
                    upload_file = open(self.translate_path(self.path) + file_name,"wb")
                    # 拷贝文件
                    while content_length > 0 :
                        chunk =  chunk if content_length > chunk else content_length
                        file_content = self.rfile.readline(chunk)
                        upload_file.write(file_content)
                        content_length -= len(file_content)
                        progress.update(upload_task,advance=len(file_content))
                    upload_file.close()
                data = {
                    'code': '0',
                    'msg': 'Success',
                    'data':{}
                }
                self.send_response(200)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps(data).encode('utf-8'))
        except Exception as e:
            print(e)
            self.log_error("发生错误 %s", e)
            data = {
                    'code': '500',
                    'msg': 'Fail',
                    'data':{}
                }
            self.send_response(500)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps(data).encode('utf-8'))
            ConsoleProgressSingleton().__exit__()



if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument('--bind', '-b', metavar='ADDRESS',
                        help='Specify alternate bind address '
                             '[default: all interfaces]')
    parser.add_argument('--directory', '-d', default=os.getcwd(),
                        help='Specify alternative directory '
                        '[default:current directory]')
    parser.add_argument('port', action='store',
                        default=4254, type=int,
                        nargs='?',
                        help='Specify alternate port [default: 4254]')
    args = parser.parse_args()
    handler_class = partial(DuplexHTTPRequestHandler,
                                directory=args.directory)

    # ensure dual-stack is not disabled; ref #38907
    class DualStackServer(http.server.ThreadingHTTPServer):
        def server_bind(self):
            # suppress exception when protocol is IPv4
            with contextlib.suppress(Exception):
                self.socket.setsockopt(
                    socket.IPPROTO_IPV6, socket.IPV6_V6ONLY, 0)
            return super().server_bind()

    http.server.test(
        HandlerClass=handler_class,
        ServerClass=DualStackServer,
        port=args.port,
        bind=args.bind,
    )