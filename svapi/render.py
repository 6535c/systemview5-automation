"""Render an owned native graph window to PNG, using only Windows and stdlib."""
import ctypes as C
from ctypes import wintypes as W
import hashlib,struct,zlib,time
from pathlib import Path
from svctl import BridgeError


class BitmapInfo(C.Structure):
    _fields_=[('size',W.DWORD),('width',W.LONG),('height',W.LONG),('planes',W.WORD),
              ('bits',W.WORD),('compression',W.DWORD),('image_size',W.DWORD),
              ('xppm',W.LONG),('yppm',W.LONG),('colors',W.DWORD),('important',W.DWORD)]


def chunk(kind,data):
    return struct.pack('!I',len(data))+kind+data+struct.pack('!I',zlib.crc32(kind+data)&0xffffffff)


def render_plot(session,plot_name,output,width=1280,height=460):
    output=Path(output).resolve()
    if output.suffix.lower()!='.png' or output.exists():raise BridgeError('Native graph render requires a new .png path')
    matches=[p for p in session.plots() if p['text'].split(':',1)[0]==plot_name]
    if len(matches)!=1:raise BridgeError('Expected exactly one native graph')
    hwnd=session.handle(matches[0]['hwnd']);u=session.win.u;g=C.WinDLL('gdi32',use_last_error=True)
    for name,ret,args in [
        ('MoveWindow',W.BOOL,[W.HWND,C.c_int,C.c_int,C.c_int,C.c_int,W.BOOL]),
        ('ShowWindow',W.BOOL,[W.HWND,C.c_int]),
        ('GetClientRect',W.BOOL,[W.HWND,C.POINTER(W.RECT)]),
        ('GetDC',W.HDC,[W.HWND]),('ReleaseDC',C.c_int,[W.HWND,W.HDC]),
        ('PrintWindow',W.BOOL,[W.HWND,W.HDC,W.UINT])]:
        f=getattr(u,name);f.restype,f.argtypes=ret,args
    for name,ret,args in [
        ('CreateCompatibleDC',W.HDC,[W.HDC]),('CreateCompatibleBitmap',W.HBITMAP,[W.HDC,C.c_int,C.c_int]),
        ('SelectObject',W.HANDLE,[W.HDC,W.HANDLE]),('DeleteObject',W.BOOL,[W.HANDLE]),
        ('DeleteDC',W.BOOL,[W.HDC]),
        ('GetDIBits',C.c_int,[W.HDC,W.HBITMAP,W.UINT,W.UINT,C.c_void_p,C.POINTER(BitmapInfo),W.UINT])]:
        f=getattr(g,name);f.restype,f.argtypes=ret,args
    frame=session.handle(session.frame('analysis'));u.ShowWindow(frame,9)
    frame_width=min(width+20,u.GetSystemMetrics(0));frame_height=min(height+140,u.GetSystemMetrics(1))
    if not u.MoveWindow(frame,0,0,frame_width,frame_height,True):raise BridgeError('Cannot size analysis frame')
    parent=u.GetParent(hwnd);session.win.send(parent,0x222,hwnd)
    session.win.send(parent,0x225,hwnd) # maximize this MDI graph inside its own frame
    # VB6 queues its layout/replot after WM_SIZE. Render the graph's own outer
    # picture box after geometry settles, rather than the MDI form/chrome.
    hwnd=session.control(hwnd,cid=3,cls='PictureBox')
    previous=None;stable=0
    for _ in range(25):
        rect=W.RECT();u.GetClientRect(hwnd,C.byref(rect));size=(rect.right,rect.bottom)
        stable=stable+1 if size==previous else 0;previous=size
        if stable>=3:break
        time.sleep(.1)
    w,h=previous
    session.win.send(hwnd,0xF)
    if w<=0 or h<=0:raise BridgeError('Native graph has no client area')
    dc=u.GetDC(hwnd);memory=g.CreateCompatibleDC(dc);bitmap=g.CreateCompatibleBitmap(dc,w,h)
    if not dc or not memory or not bitmap:raise BridgeError('Cannot allocate graph rendering surface')
    old=g.SelectObject(memory,bitmap)
    try:
        if not u.PrintWindow(hwnd,memory,3):raise BridgeError('Native graph PrintWindow failed')
        g.SelectObject(memory,old)
        info=BitmapInfo(C.sizeof(BitmapInfo),w,-h,1,32,0,w*h*4,0,0,0,0)
        buf=C.create_string_buffer(w*h*4)
        if g.GetDIBits(memory,bitmap,0,h,buf,C.byref(info),0)!=h:raise BridgeError('Cannot read rendered native graph')
        raw=buf.raw;scanlines=bytearray()
        for y in range(h):
            row=raw[y*w*4:(y+1)*w*4];rgb=bytearray(w*3)
            rgb[0::3]=row[2::4];rgb[1::3]=row[1::4];rgb[2::3]=row[0::4]
            scanlines.append(0);scanlines.extend(rgb)
        png=b'\x89PNG\r\n\x1a\n'+chunk(b'IHDR',struct.pack('!IIBBBBB',w,h,8,2,0,0,0))+chunk(b'IDAT',zlib.compress(scanlines,6))+chunk(b'IEND',b'')
        output.parent.mkdir(parents=True,exist_ok=True);output.write_bytes(png)
        return {'path':str(output),'native_plot':matches[0]['text'],'width':w,'height':h,
                'bytes':len(png),'sha256':hashlib.sha256(png).hexdigest()}
    finally:
        g.SelectObject(memory,old);g.DeleteObject(bitmap);g.DeleteDC(memory);u.ReleaseDC(hwnd,dc)
