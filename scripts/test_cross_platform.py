#!/usr/bin/env python3
"""Localhost-only OpenSSH and RFB smoke test. Never connects to OSU."""
import json, os, platform, pathlib, shutil, socket, struct, subprocess, tempfile, threading, time, traceback
from contextlib import suppress
from datetime import datetime, timezone

ROOT = pathlib.Path(__file__).resolve().parents[1]
REPORT = ROOT / "reports"
REPORT.mkdir(exist_ok=True)
tests = []

def record(name, status, detail):
    tests.append({"name": name, "status": status, "detail": str(detail)})
    print(f"[{status}] {name}: {detail}", flush=True)

def exact(s, n):
    data = b""
    while len(data) < n:
        block = s.recv(n - len(data))
        if not block: raise EOFError(f"Expected {n}, got {len(data)}")
        data += block
    return data

class Listener:
    def __init__(self):
        self.sock = socket.socket()
        self.sock.bind(("127.0.0.1", 0))
        self.sock.listen(5)
        self.sock.settimeout(.25)
        self.port = self.sock.getsockname()[1]
        self.stop = threading.Event()
        self.thread = threading.Thread(target=self.loop, daemon=True)
        self.thread.start()
    def loop(self):
        while not self.stop.is_set():
            try: s, _ = self.sock.accept()
            except socket.timeout: continue
            except OSError: break
            threading.Thread(target=self.serve, args=(s,), daemon=True).start()
    def close(self):
        self.stop.set()
        self.sock.close()
        self.thread.join(timeout=2)

class RFB(Listener):
    def serve(self, s):
        with s:
            s.settimeout(8)
            try:
                s.sendall(b"RFB 003.008\n")
                assert exact(s, 12) == b"RFB 003.008\n"
                s.sendall(b"\x01\x01")
                assert exact(s, 1) == b"\x01"
                s.sendall(b"\0\0\0\0")
                exact(s, 1)
                pixel = struct.pack(">BBBBHHHBBBxxx",32,24,0,1,255,255,255,16,8,0)
                name = b"LOCAL TEST"
                s.sendall(struct.pack(">HH",16,16)+pixel+struct.pack(">I",len(name))+name)
                while not self.stop.is_set():
                    msg = exact(s,1)[0]
                    if msg == 3:
                        exact(s,9)
                        s.sendall(struct.pack(">BBH",0,0,1)+struct.pack(">HHHHi",0,0,16,16,0)+bytes(16*16*4))
                    elif msg == 2:
                        _, count = struct.unpack(">BH",exact(s,3)); exact(s,4*count)
                    elif msg == 0: exact(s,19)
                    elif msg == 4: exact(s,7)
                    elif msg == 5: exact(s,5)
                    else: break
            except (OSError, EOFError, AssertionError, TimeoutError): pass

def request_frame(port):
    with socket.create_connection(("127.0.0.1",port),timeout=8) as s:
        s.settimeout(8)
        assert exact(s,12) == b"RFB 003.008\n"
        s.sendall(b"RFB 003.008\n")
        assert exact(s,2) == b"\x01\x01"
        s.sendall(b"\x01")
        assert exact(s,4) == b"\0\0\0\0"
        s.sendall(b"\x01")
        head = exact(s,24)
        width,height=struct.unpack(">HH",head[:4])
        namelen=struct.unpack(">I",head[20:24])[0]
        exact(s,namelen)
        s.sendall(struct.pack(">BBHHHH",3,0,0,0,width,height))
        assert exact(s,4) == b"\0\0\0\x01"
        rect=exact(s,12)
        assert struct.unpack(">HHHHi",rect)[-1] == 0
        frame=exact(s,width*height*4)
        assert (width,height,len(frame)) == (16,16,1024)
        return "RFB 3.8, 16x16 framebuffer (1024 bytes)"

def check_ssh():
    import paramiko
    class Auth(paramiko.ServerInterface):
        def __init__(self, key, port):
            self.key,self.port=key,port
        def get_allowed_auths(self, user): return "publickey"
        def check_auth_publickey(self,user,key):
            return paramiko.AUTH_SUCCESSFUL if user == "ci" and key.get_base64() == self.key else paramiko.AUTH_FAILED
        def check_channel_direct_tcpip_request(self, chanid, origin, destination):
            return paramiko.OPEN_SUCCEEDED if destination == ("127.0.0.1",self.port) else paramiko.OPEN_FAILED_ADMINISTRATIVELY_PROHIBITED
    class SSH(Listener):
        def __init__(self, key, port):
            self.key,self.target=key,port
            self.hostkey=paramiko.RSAKey.generate(2048)
            self.transports=[]
            super().__init__()
        def serve(self,s):
            t=paramiko.Transport(s)
            self.transports.append(t)
            try:
                t.add_server_key(self.hostkey)
                t.start_server(server=Auth(self.key,self.target))
                while t.is_active() and not self.stop.is_set():
                    channel=t.accept(.3)
                    if channel: threading.Thread(target=self.relay,args=(channel,),daemon=True).start()
            except (OSError,EOFError,paramiko.SSHException): pass
            finally: t.close()
        def relay(self, channel):
            try: downstream=socket.create_connection(("127.0.0.1",self.target),timeout=8)
            except OSError: channel.close(); return
            def pump(src,dst):
                try:
                    while True:
                        buf=src.recv(65536)
                        if not buf: break
                        dst.sendall(buf)
                except (OSError,EOFError,socket.timeout): pass
                finally:
                    with suppress(Exception):
                        if isinstance(dst,paramiko.Channel): dst.shutdown_write()
                        else: dst.shutdown(socket.SHUT_WR)
            with channel,downstream:
                downstream.settimeout(8)
                back=threading.Thread(target=pump,args=(channel,downstream),daemon=True)
                back.start()
                pump(downstream,channel)
                back.join(timeout=2)
        def close(self):
            super().close()
            for t in self.transports:
                with suppress(Exception): t.close()
    ssh=shutil.which("ssh"); keygen=shutil.which("ssh-keygen")
    if not ssh or not keygen: raise RuntimeError("Missing native OpenSSH client or keygen")
    record("openssh-client","PASS",ssh)
    with tempfile.TemporaryDirectory() as directory:
        temp=pathlib.Path(directory); identity=temp/"id_ed25519"
        subprocess.run([keygen,"-q","-t","ed25519","-N","","-f",str(identity)],check=True,timeout=20)
        pub=identity.with_suffix(".pub").read_text().split()[1]
        vnc=RFB(); gateway=SSH(pub,vnc.port)
        sock=socket.socket();sock.bind(("127.0.0.1",0));local=sock.getsockname()[1];sock.close()
        stderr=(REPORT/"ssh-stderr.txt").open("w")
        command=[ssh,"-F","none","-p",str(gateway.port),"-i",str(identity),"-o","BatchMode=yes",
                 "-o","IdentitiesOnly=yes","-o","StrictHostKeyChecking=accept-new",
                 "-o","UserKnownHostsFile="+str(temp/"known_hosts"),
                 "-o","ExitOnForwardFailure=yes","-N","-L",
                 f"127.0.0.1:{local}:127.0.0.1:{vnc.port}","ci@127.0.0.1"]
        process=subprocess.Popen(command,stdin=subprocess.DEVNULL,stderr=stderr,stdout=subprocess.DEVNULL)
        try:
            deadline=time.monotonic()+15
            while time.monotonic()<deadline:
                if process.poll() is not None: raise RuntimeError("SSH exited early; see ssh-stderr.txt")
                with socket.socket() as probe:
                    if probe.connect_ex(("127.0.0.1",local)) == 0: break
                time.sleep(.15)
            else: raise TimeoutError("SSH tunnel listener did not start")
            record("openssh-forwarded-vnc","PASS",request_frame(local))
        finally:
            process.terminate()
            with suppress(Exception): process.wait(timeout=5)
            if process.poll() is None: process.kill()
            stderr.close();gateway.close();vnc.close()

def viewer_path():
    if platform.system()=="Windows":
        return pathlib.Path(os.environ.get("ProgramFiles",r"C:\Program Files"))/"TurboVNC"/"vncviewer.bat"
    if platform.system()=="Darwin": return pathlib.Path("/opt/TurboVNC/bin/vncviewer")
    found=shutil.which("vncviewer")
    return pathlib.Path(found) if found else pathlib.Path("/usr/bin/vncviewer")

def main():
    viewer=viewer_path()
    record("platform","PASS",platform.platform())
    record("viewer-installed","PASS" if viewer.is_file() else "FAIL",str(viewer))
    if viewer.is_file():
        cmd=["cmd","/c",str(viewer),"-?"] if platform.system()=="Windows" else (
            [str(viewer),"-?"] if platform.system()=="Darwin" else
            ["xvfb-run","-a",str(viewer),"-help"])
        try:
            p=subprocess.run(cmd,capture_output=True,text=True,timeout=20,errors="replace")
            output=(p.stdout or "")+"\n"+(p.stderr or "")
            (REPORT/"viewer-cli.txt").write_text(output[:30000],encoding="utf-8")
            record("viewer-cli","PASS" if ("usage" in output.lower() or "options" in output.lower()) and p.returncode in (0,1) else "WARN",f"Exit {p.returncode}; CLI output saved")
        except Exception as e:record("viewer-cli","WARN",str(e))
    try:check_ssh()
    except Exception as e:
        record("openssh-forwarded-vnc","FAIL",repr(e))
        (REPORT/"exception.txt").write_text(traceback.format_exc())
    report={"timestamp":datetime.now(timezone.utc).isoformat(),"system":platform.platform(),
            "runner":os.environ.get("RUNNER_OS","local"),"tests":tests,
            "passed":sum(t["status"]=="PASS" for t in tests),
            "failed":sum(t["status"]=="FAIL" for t in tests)}
    (REPORT/"results.json").write_text(json.dumps(report,indent=2))
    summary=f'# {report["runner"]}: {report["passed"]} PASS, {report["failed"]} FAIL\n\n'
    summary+="| Test | Result | Details |\n|---|---|---|\n"
    summary+="".join(f'| {t["name"]} | {t["status"]} | {t["detail"].replace("|","/")} |\n' for t in tests)
    summary+="\nTests use only local disposable services. **Not a real OSU or Cadence connection.**\n"
    (REPORT/"summary.md").write_text(summary)
    print(summary)
    if os.environ.get("GITHUB_STEP_SUMMARY"):
        with open(os.environ["GITHUB_STEP_SUMMARY"],"a") as f: f.write(summary)
    return 1 if report["failed"] else 0

if __name__=="__main__":
    raise SystemExit(main())
