#!/usr/bin/env python3
"""Wire EDM Post-Processor  —  SKD2 / EAPT   by Arturo Rebolledo"""
import tkinter as tk
from tkinter import ttk, filedialog, scrolledtext
import math, os, sys, json

__version__='1.1.0'

try:
    import ezdxf
except ImportError:
    import subprocess
    subprocess.call([sys.executable,'-m','pip','install','ezdxf','--break-system-packages','-q'])
    import ezdxf

# ═══════════════════════════════════════════════════
#  UNIDADES
# ═══════════════════════════════════════════════════
DXF_SCALE={0:1.,1:25.4,2:304.8,4:1.,5:10.,6:1000.,14:.001}
DXF_NAME ={0:'?',1:'pulg',2:'pies',4:'mm',5:'cm',6:'m',14:'µm'}

# ═══════════════════════════════════════════════════
#  GEOMETRÍA BASE
# ═══════════════════════════════════════════════════
def mm2um(v):       return int(round(v*1000))
def xy(x,y):        return f"X{mm2um(x)}Y{mm2um(y)}"
def pdist(a,b):     return math.hypot(b[0]-a[0],b[1]-a[1])
def ang(cx,cy,r,d): a=math.radians(d); return cx+r*math.cos(a),cy+r*math.sin(a)
def norm_d(d):      return d%360.

def signed_area(pts):
    n=len(pts);s=0.
    for i in range(n):
        x1,y1=pts[i];x2,y2=pts[(i+1)%n];s+=(x1*y2-x2*y1)
    return s/2.

def seg_tangent(seg):
    t=seg['type'];sx,sy=seg['start']
    if t=='LINE':
        ex,ey=seg['end'];d=math.hypot(ex-sx,ey-sy)
        return ((ex-sx)/d,(ey-sy)/d) if d>1e-9 else (1.,0.)
    elif t=='ARC':
        cx,cy=seg['cx'],seg['cy'];dx,dy=sx-cx,sy-cy;r=math.hypot(dx,dy)
        if r<1e-9: return 1.,0.
        return (dy/r,-dx/r) if seg.get('ccw',True) else (-dy/r,dx/r)
    return 1.,0.

def perp_pt(seg,length):
    tx,ty=seg_tangent(seg);sx,sy=seg['start']
    return sx-ty*length,sy+tx*length

def seg_dist(seg,wx,wy):
    t=seg['type']
    if t=='LINE':
        sx,sy=seg['start'];ex,ey=seg['end']
        dx,dy=ex-sx,ey-sy;l2=dx*dx+dy*dy
        if l2<1e-9: return pdist((wx,wy),(sx,sy))
        tt=max(0.,min(1.,((wx-sx)*dx+(wy-sy)*dy)/l2))
        return pdist((wx,wy),(sx+tt*dx,sy+tt*dy))
    elif t=='ARC':
        # Distancia al ARCO visible, no al círculo completo — si el ángulo del
        # punto cae fuera del arco, medir contra los extremos del arco.
        cx,cy=seg['cx'],seg['cy']
        a=norm_d(math.degrees(math.atan2(wy-cy,wx-cx)))
        if _angle_on_arc(a,seg['sa'],seg['ea'],seg.get('ccw',True)):
            return abs(pdist((wx,wy),(cx,cy))-seg['r'])
        return min(pdist((wx,wy),seg['start']),pdist((wx,wy),seg['end']))
    return float('inf')

# ═══════════════════════════════════════════════════
#  INTERSECCIONES (para Trim)
# ═══════════════════════════════════════════════════
def line_line_intersect(p1,p2,p3,p4):
    """Retorna (punto,(t,s)) si los segmentos se intersectan, None si no."""
    d1x,d1y=p2[0]-p1[0],p2[1]-p1[1]
    d2x,d2y=p4[0]-p3[0],p4[1]-p3[1]
    denom=d1x*d2y-d1y*d2x
    if abs(denom)<1e-12: return None
    dx,dy=p3[0]-p1[0],p3[1]-p1[1]
    t=(dx*d2y-dy*d2x)/denom
    s=(dx*d1y-dy*d1x)/denom
    if -1e-4<=t<=1+1e-4 and -1e-4<=s<=1+1e-4:
        return (p1[0]+t*d1x,p1[1]+t*d1y),(t,s)
    return None

def line_arc_intersects(p1,p2,cx,cy,r,sa,ea,ccw):
    """Retorna lista de (punto, t_en_linea, angulo_en_arco)."""
    dx,dy=p2[0]-p1[0],p2[1]-p1[1]
    fx,fy=p1[0]-cx,p1[1]-cy
    a=dx*dx+dy*dy; b=2*(fx*dx+fy*dy); c=fx*fx+fy*fy-r*r
    disc=b*b-4*a*c
    if disc<0 or a<1e-18: return []
    results=[]
    for sign in (+1,-1):
        t=(-b+sign*math.sqrt(max(disc,0)))/(2*a)
        if -1e-4<=t<=1+1e-4:
            px,py=p1[0]+t*dx,p1[1]+t*dy
            angle=norm_d(math.degrees(math.atan2(py-cy,px-cx)))
            if _angle_on_arc(angle,sa,ea,ccw):
                results.append(((px,py),t,angle))
    return results

def _angle_on_arc(angle,sa,ea,ccw):
    if ccw:
        span=(ea-sa)%360
        if span<1e-6: span=360.
        return ((angle-sa)%360)<=span+1e-4
    else:
        span=(sa-ea)%360
        if span<1e-6: span=360.
        return ((sa-angle)%360)<=span+1e-4

def find_intersections(sA,sB):
    """Todas las intersecciones entre sA y sB. Retorna lista de (punto,tA,tB)."""
    tA,tB=sA['type'],sB['type']
    results=[]
    if tA=='LINE' and tB=='LINE':
        r=line_line_intersect(sA['start'],sA['end'],sB['start'],sB['end'])
        if r: results.append((r[0],r[1][0],r[1][1]))
    elif tA=='LINE' and tB=='ARC':
        for pt,t,angle in line_arc_intersects(sA['start'],sA['end'],
                sB['cx'],sB['cy'],sB['r'],sB['sa'],sB['ea'],sB.get('ccw',True)):
            results.append((pt,t,angle))
    elif tA=='ARC' and tB=='LINE':
        for pt,t,angle in line_arc_intersects(sB['start'],sB['end'],
                sA['cx'],sA['cy'],sA['r'],sA['sa'],sA['ea'],sA.get('ccw',True)):
            results.append((pt,angle,t))
    return results

def split_line(seg,pt):
    s={'type':'LINE','start':seg['start'],'end':pt}
    e={'type':'LINE','start':pt,'end':seg['end']}
    return s,e

def split_arc(seg,angle):
    pt=ang(seg['cx'],seg['cy'],seg['r'],angle)
    s=dict(seg);s['end']=pt;s['ea']=angle
    e=dict(seg);e['start']=pt;e['sa']=angle
    return s,e

# ═══════════════════════════════════════════════════
#  LECTURA DXF
# ═══════════════════════════════════════════════════
def _read_dxf_raw(path, layer=None):
    """Parser DXF mínimo que lee directamente del texto — tolera handles inválidos."""
    segs=[]
    code=0   # INSUNITS default
    with open(path,'r',errors='ignore') as f:
        lines=[l.rstrip('\n\r') for l in f]
    # Detectar INSUNITS del header
    for i,l in enumerate(lines):
        if l.strip()=='$INSUNITS' and i+2<len(lines) and lines[i+1].strip()=='70':
            try: code=int(lines[i+2].strip()); break
            except: pass
    sc=DXF_SCALE.get(code,1.); units=DXF_NAME.get(code,'?')
    def s(v): return float(v)*sc

    i=0; n=len(lines)
    while i<n:
        etype=lines[i].strip()
        if etype not in ('LINE','ARC','CIRCLE','LWPOLYLINE','SPLINE'):
            i+=1; continue
        # Leer tags del bloque hasta siguiente entidad o ENDSEC
        tags={}; i+=1
        while i<n:
            raw=lines[i].strip()
            try: gcode=int(raw)
            except: i+=1; break
            val=lines[i+1].strip() if i+1<n else ''
            tags.setdefault(gcode,[]).append(val)
            i+=2
            if gcode==0: i-=2; break   # siguiente entidad
        # Filtrar por layer si se pide
        cur_layer=tags.get(8,[''])[0]
        if layer and cur_layer.upper()!=layer.upper(): continue
        try:
            if etype=='LINE':
                x1=s(tags[10][0]);y1=s(tags[20][0])
                x2=s(tags[11][0]);y2=s(tags[21][0])
                segs.append({'type':'LINE','start':(x1,y1),'end':(x2,y2)})
            elif etype=='ARC':
                cx=s(tags[10][0]);cy=s(tags[20][0]);r=s(tags[40][0])
                sa=norm_d(float(tags[50][0]));ea=norm_d(float(tags[51][0]))
                segs.append({'type':'ARC','cx':cx,'cy':cy,'r':r,'sa':sa,'ea':ea,'ccw':True,
                             'start':ang(cx,cy,r,sa),'end':ang(cx,cy,r,ea)})
            elif etype=='CIRCLE':
                cx=s(tags[10][0]);cy=s(tags[20][0]);r=s(tags[40][0])
                segs.append({'type':'ARC','cx':cx,'cy':cy,'r':r,'sa':0.,'ea':180.,'ccw':True,
                             'start':ang(cx,cy,r,0.),'end':ang(cx,cy,r,180.)})
                segs.append({'type':'ARC','cx':cx,'cy':cy,'r':r,'sa':180.,'ea':0.,'ccw':True,
                             'start':ang(cx,cy,r,180.),'end':ang(cx,cy,r,0.)})
        except (KeyError,IndexError,ValueError):
            pass
    return segs,sc,units

def read_dxf(path,layer=None):
    try:
        doc=ezdxf.readfile(path)
    except Exception:
        # DXF con handles inválidos — usar parser directo
        return _read_dxf_raw(path,layer)
    msp=doc.modelspace()
    code=doc.header.get('$INSUNITS',0)
    sc=DXF_SCALE.get(code,1.);units=DXF_NAME.get(code,'?')
    segs=[]
    def s(v): return v*sc
    for ent in msp:
        if layer and ent.dxf.layer.upper()!=layer.upper(): continue
        t=ent.dxftype()
        if t=='LINE':
            p1,p2=ent.dxf.start,ent.dxf.end
            segs.append({'type':'LINE','start':(s(p1.x),s(p1.y)),'end':(s(p2.x),s(p2.y))})
        elif t=='ARC':
            cx,cy,r=s(ent.dxf.center.x),s(ent.dxf.center.y),s(ent.dxf.radius)
            sa=norm_d(ent.dxf.start_angle);ea=norm_d(ent.dxf.end_angle)
            segs.append({'type':'ARC','cx':cx,'cy':cy,'r':r,'sa':sa,'ea':ea,'ccw':True,
                         'start':ang(cx,cy,r,sa),'end':ang(cx,cy,r,ea)})
        elif t=='CIRCLE':
            cx,cy,r=s(ent.dxf.center.x),s(ent.dxf.center.y),s(ent.dxf.radius)
            segs.append({'type':'ARC','cx':cx,'cy':cy,'r':r,'sa':0.,'ea':180.,'ccw':True,
                         'start':ang(cx,cy,r,0.),'end':ang(cx,cy,r,180.)})
            segs.append({'type':'ARC','cx':cx,'cy':cy,'r':r,'sa':180.,'ea':0.,'ccw':True,
                         'start':ang(cx,cy,r,180.),'end':ang(cx,cy,r,0.)})
        elif t=='LWPOLYLINE':
            pts=list(ent.get_points(format='xyb'))
            if ent.closed: pts.append(pts[0])
            for i in range(len(pts)-1):
                x1,y1,bulge=pts[i][0],pts[i][1],pts[i][2]
                x2,y2=pts[i+1][0],pts[i+1][1]
                x1,y1,x2,y2=s(x1),s(y1),s(x2),s(y2)
                if abs(bulge)<1e-9: segs.append({'type':'LINE','start':(x1,y1),'end':(x2,y2)})
                else: segs.append(_bulge(x1,y1,x2,y2,bulge))
        elif t=='SPLINE':
            pts2=list(ent.flattening(0.01))
            for i in range(len(pts2)-1):
                p1,p2=pts2[i],pts2[i+1]
                segs.append({'type':'LINE','start':(s(p1.x),s(p1.y)),'end':(s(p2.x),s(p2.y))})
    return segs,sc,units

def _bulge(x1,y1,x2,y2,bulge):
    theta=4*math.atan(abs(bulge));d=math.hypot(x2-x1,y2-y1)
    r=d/(2*math.sin(theta/2));ach=math.atan2(y2-y1,x2-x1)
    h=math.sqrt(max(r*r-(d/2)**2,0));sign=1 if bulge>0 else -1
    cx=(x1+x2)/2-sign*h*math.sin(ach);cy=(y1+y2)/2+sign*h*math.cos(ach)
    sa=norm_d(math.degrees(math.atan2(y1-cy,x1-cx)))
    ea=norm_d(math.degrees(math.atan2(y2-cy,x2-cx)))
    return {'type':'ARC','cx':cx,'cy':cy,'r':r,'sa':sa,'ea':ea,'ccw':bulge>0,
            'start':(x1,y1),'end':(x2,y2)}

# ═══════════════════════════════════════════════════
#  CONTORNOS
# ═══════════════════════════════════════════════════
TOL=0.5

def find_contours(segs):
    pool=list(segs);contours=[]
    while pool:
        cur=[pool.pop(0)];ch=True
        while ch:
            ch=False;tail=cur[-1]['end'];head=cur[0]['start']
            # Find the CLOSEST match within TOL (not just the first) so that
            # perfectly-fitting connector arcs (0 mm gap) are never skipped in
            # favour of a segment that is merely within the tolerance distance.
            best_i=None;best_d=TOL;best_where=None;best_flip=False
            for i,seg in enumerate(pool):
                for d,where,flip in [
                    (pdist(tail,seg['start']),'tail',False),
                    (pdist(tail,seg['end']),  'tail',True),
                    (pdist(head,seg['end']),  'head',False),
                    (pdist(head,seg['start']),'head',True),
                ]:
                    if d<best_d:
                        best_d=d;best_i=i;best_where=where;best_flip=flip
            if best_i is not None:
                s=pool.pop(best_i)
                if best_flip: s=_flip(s)
                if best_where=='tail': cur.append(s)
                else:                  cur.insert(0,s)
                ch=True
        contours.append(cur)
    contours.sort(key=lambda c:_clen(c),reverse=True)
    return contours

def _clen(c):
    t=0.
    for seg in c:
        if seg['type']=='LINE': t+=pdist(seg['start'],seg['end'])
        elif seg['type']=='ARC':
            sa,ea,ccw=seg['sa'],seg['ea'],seg.get('ccw',True)
            da=(ea-sa)%360 if ccw else (sa-ea)%360
            if da<1e-6: da=360.
            t+=math.radians(da)*seg['r']
    return t

def _flip(seg):
    s=dict(seg);s['start'],s['end']=seg['end'],seg['start']
    if seg['type']=='ARC': s['sa'],s['ea']=seg['ea'],seg['sa'];s['ccw']=not seg['ccw']
    return s

def rotate_segs(segs, angle_deg):
    if not segs or abs(angle_deg)<1e-9: return segs
    all_pts=[pt for seg in segs for pt in [seg['start'],seg['end']]]
    cx=sum(p[0] for p in all_pts)/len(all_pts)
    cy=sum(p[1] for p in all_pts)/len(all_pts)
    rad=math.radians(angle_deg); ca=math.cos(rad); sa=math.sin(rad)
    def rp(x,y):
        dx,dy=x-cx,y-cy
        return cx+dx*ca-dy*sa, cy+dx*sa+dy*ca
    result=[]
    for seg in segs:
        s=dict(seg)
        s['start']=rp(*seg['start']); s['end']=rp(*seg['end'])
        if seg['type']=='ARC':
            s['cx'],s['cy']=rp(seg['cx'],seg['cy'])
            s['sa']=norm_d(seg['sa']+angle_deg)
            s['ea']=norm_d(seg['ea']+angle_deg)
        result.append(s)
    return result

def rotate_chain(c,idx):
    if not c or idx==0: return c
    return c[idx:]+c[:idx]

def contour_dir(c):
    return 'CCW' if signed_area([s['start'] for s in c])>=0 else 'CW'

def rev(c): return [_flip(s) for s in reversed(c)]

def overcut_pt(c,dm):
    if dm<=.001: return c[0]['start']
    rem=dm
    for seg in c:
        if seg['type']=='LINE':
            sl=pdist(seg['start'],seg['end'])
            if rem<=sl:
                f=rem/sl;sx,sy=seg['start'];ex,ey=seg['end']
                return sx+f*(ex-sx),sy+f*(ey-sy)
            rem-=sl
        elif seg['type']=='ARC':
            r=seg['r'];ccw=seg['ccw'];sa,ea=seg['sa'],seg['ea']
            da=(ea-sa)%360 if ccw else (sa-ea)%360
            if da<1e-6: da=360.
            al=math.radians(da)*r
            if rem<=al:
                pt_a=norm_d(sa+da*(rem/al)) if ccw else norm_d(sa-da*(rem/al))
                return ang(seg['cx'],seg['cy'],r,pt_a)
            rem-=al
    return c[0]['start']

def seg_to_g(seg):
    t=seg['type'];ex,ey=seg['end']
    if t=='LINE': return f"G01{xy(ex,ey)}"
    elif t=='ARC':
        sx,sy=seg['start'];cx,cy=seg['cx'],seg['cy']
        g='G03' if seg['ccw'] else 'G02'
        return f"{g}X{mm2um(ex)}Y{mm2um(ey)}I{mm2um(cx-sx)}J{mm2um(cy-sy)}"
    return ''

# ═══════════════════════════════════════════════════
#  KERF (trayectoria compensada) Y CHEQUEO DE GOUGE
# ═══════════════════════════════════════════════════
def kerf_seg_pts(seg,comp,d):
    """Puntos del camino REAL del hilo (compensado G41/G42 por d mm)."""
    if d<=1e-9: return []
    left=(comp=='G41')
    if seg['type']=='LINE':
        tx,ty=seg_tangent(seg)
        nx,ny=(-ty,tx) if left else (ty,-tx)
        (x0,y0),(x1,y1)=seg['start'],seg['end']
        return [(x0+nx*d,y0+ny*d),(x1+nx*d,y1+ny*d)]
    elif seg['type']=='ARC':
        ccw=seg.get('ccw',True)
        toward_center=(ccw and left) or ((not ccw) and (not left))
        r2=seg['r']-d if toward_center else seg['r']+d
        if r2<=1e-9: return []
        cx,cy=seg['cx'],seg['cy'];sa,ea=seg['sa'],seg['ea']
        span=(ea-sa)%360 if ccw else -((sa-ea)%360)
        if abs(span)<1e-6: span=360. if ccw else -360.
        n=max(8,int(abs(span)/4))
        return [ang(cx,cy,r2,sa+span*t/n) for t in range(n+1)]
    return []

def gouge_check(chained,comp,d):
    """Arcos con radio interno ≤ offset → la máquina alarmea o gougea.
    Retorna lista de (x,y,mensaje) en el punto medio del arco problemático."""
    warns=[];left=(comp=='G41')
    for i,seg in enumerate(chained):
        if seg['type']!='ARC': continue
        ccw=seg.get('ccw',True)
        toward_center=(ccw and left) or ((not ccw) and (not left))
        if toward_center and seg['r']<=d+1e-9:
            sa,ea=seg['sa'],seg['ea']
            span=(ea-sa)%360 if ccw else (sa-ea)%360
            if span<1e-6: span=360.
            mid=norm_d(sa+span/2) if ccw else norm_d(sa-span/2)
            mx,my=ang(seg['cx'],seg['cy'],seg['r'],mid)
            warns.append((mx,my,f'Seg {i+1}: R{seg["r"]:.3f}mm ≤ offset {d:.3f}mm'))
    return warns

# ═══════════════════════════════════════════════════
#  GENERADOR ISO
# ═══════════════════════════════════════════════════
def generate_iso(chained,p):
    if not chained: raise ValueError("Sin segmentos.")
    mode=p['mode'];cuts=p['cuts']
    direction=contour_dir(chained)
    if mode=='Cavity' and direction=='CCW': chained=rev(chained);direction='CW'
    elif mode=='Core'  and direction=='CW':  chained=rev(chained);direction='CCW'

    comp=p['comp']
    if comp=='auto': comp='G41' if mode=='Core' else 'G42'

    sx,sy=chained[0]['start']

    cutin=p['cutin'];ll=p['leadin_length']
    # Calcular lead-in primero
    lx=p.get('leadin_x');ly=p.get('leadin_y')
    leadin_angle=p.get('leadin_angle')
    if lx is None:
        if leadin_angle is not None:
            a=math.radians(leadin_angle)
            lx=sx-ll*math.cos(a);ly=sy-ll*math.sin(a)
        elif cutin=='perp': lx,ly=perp_pt(chained[0],ll)
        elif cutin=='line':
            _tx=p['thread_x'] if p['thread_x'] is not None else sx
            _ty=p['thread_y'] if p['thread_y'] is not None else sy
            d=pdist((_tx,_ty),(sx,sy))
            if d>1e-9: lx=sx+(_tx-sx)/d*ll;ly=sy+(_ty-sy)/d*ll
            else: lx,ly=sx,sy-ll
        else: lx,ly=sx,sy-ll

    # Thread: si no está definido, usar el punto de lead-in (el agujero está ahí)
    tx=p['thread_x'] if p['thread_x'] is not None else lx
    ty=p['thread_y'] if p['thread_y'] is not None else ly

    # Lead-out
    ex_lx=p.get('leadout_x');ex_ly=p.get('leadout_y')
    leadout_angle=p.get('leadout_angle')
    last_end=chained[-1]['end']
    if ex_lx is not None:
        pass   # lead-out manual libre
    elif p.get('same_lead'):
        ex_lx,ex_ly=lx,ly
    elif leadout_angle is not None:
        a=math.radians(leadout_angle)
        ex_lx=last_end[0]+ll*math.cos(a);ex_ly=last_end[1]+ll*math.sin(a)
    else:
        exit_seg_idx=p.get('exit_seg')
        if exit_seg_idx is not None and 0<=exit_seg_idx<len(chained):
            ex_lx,ex_ly=perp_pt(chained[exit_seg_idx],ll)
        else:
            ex_lx,ex_ly=perp_pt(chained[-1],ll)

    do_oc=p['overcut']>0.001;oc=overcut_pt(chained,p['overcut'])
    offsets=list(p['offsets']);eparams=list(p['eparams'])
    while len(offsets)<cuts: offsets.append(offsets[-1])
    while len(eparams)<cuts: eparams.append(eparams[-1])
    offsets=offsets[:cuts];eparams=eparams[:cuts]

    thick=p['thickness']
    ts=str(int(thick)) if thick==int(thick) else str(thick)

    # Tiempo estimado: pasada 1 a velocidad de corte, repasos ~3× más rápidos
    v_cut=p.get('cut_speed',0.)
    plen=_clen(chained)+ll*2+p['overcut']
    est=sum(plen/(v_cut*(1. if i==0 else 3.)) for i in range(cuts)) if v_cut>1e-9 else 0.

    L=[]
    L.append(f"(MATERIAL:{p['material']} THICKNESS:{ts} mm WIRE:{p['wire']}mm FLUSH:{p['flush']} MODE:{mode} CUTNUM:{cuts})")
    if est>0:
        L.append(f"(EST TIME: {int(est//60)}h {int(est%60):02d}m  PATH:{plen:.1f}mm  @{v_cut}mm/min)")
    L.append("(     W_Sp   I_Max   Pul_On    P_Ratio   Voltage   Auxiliary  Speed)")
    for i,ep in enumerate(eparams,1):
        L.append(f"E{i:03d}=   {ep['w_sp']:03d}    {ep['i_max']:03d}    {ep['pul_on']:03d}    "
                 f"{ep['p_ratio']:03d}    {ep['voltage']:03d}    {ep['aux']:03d}    {ep['speed']:03d}")
    if cuts==1: L.append(f"H001={offsets[0]} ")
    else:       L.append("  ".join(f"H{i+1:03d}={o}" for i,o in enumerate(offsets)))
    L+=["   ",f"; Number : 1",f"G92{xy(tx,ty)}","G90","H001","E001","M98 P0001","M00","   "]
    for i in range(1,cuts):
        L+=[f"H{i+1:03d}",f"E{i+1:03d}","M98 P0001","M00","   "]
    L+=["   ",f"G01{xy(tx,ty)}","M02","   ",f"N0001"]
    L+=[f"G01{xy(lx,ly)}",f"{comp}",f"G01{xy(sx,sy)}"]
    for seg in chained: L.append(seg_to_g(seg))
    if do_oc: L.append(f"G01{xy(*oc)}")
    exit_cmd='G00' if p.get('force_exit') else 'G01'
    L+=["G50","G40",f"{exit_cmd}{xy(ex_lx,ex_ly)}","M99"]

    d0=offsets[0]/1000.
    return '\r\n'.join(L),{
        'direction':direction,'comp':comp,
        'lx':lx,'ly':ly,'tx':tx,'ty':ty,'sx':sx,'sy':sy,
        'ex_lx':ex_lx,'ex_ly':ex_ly,
        'kerf':[kerf_seg_pts(s,comp,d0) for s in chained],
        'gouges':gouge_check(chained,comp,d0),
        'offset_mm':d0,'est_min':est}

# ═══════════════════════════════════════════════════
#  GENERADOR ISO MULTI-CONTORNO
# ═══════════════════════════════════════════════════
def generate_iso_multi(contours,p):
    """Un solo programa que corta TODOS los contornos de la placa.
    Interiores (más cortos) primero, perfil exterior al final — la pieza
    queda sujeta hasta el último corte. M00 entre contornos para re-enhebrar."""
    conts=[list(c) for c in contours if c]
    if not conts: raise ValueError('Sin contornos.')
    conts=sorted(conts,key=_clen)   # interiores primero, exterior al final
    mode=p['mode'];cuts=p['cuts']
    comp=p['comp']
    if comp=='auto': comp='G41' if mode=='Core' else 'G42'
    offsets=list(p['offsets']);eparams=list(p['eparams'])
    while len(offsets)<cuts: offsets.append(offsets[-1])
    while len(eparams)<cuts: eparams.append(eparams[-1])
    offsets=offsets[:cuts];eparams=eparams[:cuts]
    ll=p['leadin_length'];do_oc=p['overcut']>0.001
    exit_cmd='G00' if p.get('force_exit') else 'G01'
    thick=p['thickness']
    ts=str(int(thick)) if thick==int(thick) else str(thick)

    v_cut=p.get('cut_speed',0.)
    tlen=sum(_clen(c)+ll*2+p['overcut'] for c in conts)
    est=sum(tlen/(v_cut*(1. if i==0 else 3.)) for i in range(cuts)) if v_cut>1e-9 else 0.

    L=[]
    L.append(f"(MATERIAL:{p['material']} THICKNESS:{ts} mm WIRE:{p['wire']}mm FLUSH:{p['flush']} MODE:{mode} CUTNUM:{cuts} CONTOURS:{len(conts)})")
    if est>0:
        L.append(f"(EST TIME: {int(est//60)}h {int(est%60):02d}m  PATH:{tlen:.1f}mm  @{v_cut}mm/min)")
    L.append("(     W_Sp   I_Max   Pul_On    P_Ratio   Voltage   Auxiliary  Speed)")
    for i,ep in enumerate(eparams,1):
        L.append(f"E{i:03d}=   {ep['w_sp']:03d}    {ep['i_max']:03d}    {ep['pul_on']:03d}    "
                 f"{ep['p_ratio']:03d}    {ep['voltage']:03d}    {ep['aux']:03d}    {ep['speed']:03d}")
    if cuts==1: L.append(f"H001={offsets[0]} ")
    else:       L.append("  ".join(f"H{i+1:03d}={o}" for i,o in enumerate(offsets)))

    subs=[]
    for ci,chained in enumerate(conts,1):
        direction=contour_dir(chained)
        if mode=='Cavity' and direction=='CCW': chained=rev(chained)
        elif mode=='Core'  and direction=='CW':  chained=rev(chained)
        sx,sy=chained[0]['start']
        lx,ly=perp_pt(chained[0],ll)   # lead-in perpendicular automático
        tx,ty=lx,ly                    # agujero de enhebrado = punto de lead-in
        ex_lx,ex_ly=perp_pt(chained[-1],ll)
        oc=overcut_pt(chained,p['overcut'])

        L+=["   ",f"; Number : {ci}",f"G92{xy(tx,ty)}","G90"]
        for i in range(cuts):
            L+=[f"H{i+1:03d}",f"E{i+1:03d}",f"M98 P{ci:04d}","M00","   "]

        sub=[f"N{ci:04d}",f"G01{xy(lx,ly)}",comp,f"G01{xy(sx,sy)}"]
        for seg in chained: sub.append(seg_to_g(seg))
        if do_oc: sub.append(f"G01{xy(*oc)}")
        sub+=["G50","G40",f"{exit_cmd}{xy(ex_lx,ex_ly)}","M99"]
        subs.append(sub)

    L+=["   ","M02","   "]
    for sub in subs: L+=sub+["   "]
    return '\r\n'.join(L)

# ═══════════════════════════════════════════════════
#  CANVAS
# ═══════════════════════════════════════════════════
CC={
    'bg':'#ffffff','ref':'#c5c8cc','active':'#1a73e8','entry':'#e37400',
    'thread':'#d93025','leadin':'#1e7e34','exit':'#c45000',
    'hover':'#7c4dff','user':'#00897b','cut_edge':'#d93025','preview':'#9aa0a6'
}
SNAP_PX=14

class DXFCanvas(tk.Canvas):
    def __init__(self,parent,on_changed=None,status_cb=None,**kw):
        super().__init__(parent,bg=CC['bg'],highlightthickness=1,
                         highlightbackground=BORDER if 'BORDER' in dir() else '#dadce0',**kw)
        self.on_changed=on_changed
        self.status_cb =status_cb
        self.all_segs  =[]
        self.contours  =[]
        self.active_idx=0
        self.entry_seg =0
        self.exit_seg  =None   # índice del segmento de salida (None = último)
        self.thread_world  =None
        self.exit_world    =None
        self.leadin_world  =None   # punto de approach del lead-in (libre)
        self.leadout_world =None   # punto de approach del lead-out (libre)
        self._tool     ='select'
        self._mode     =None
        self._draw_pts =[]
        self._hover_pt =None
        self._hover_idx=None
        self._info     ={}
        self._measure  =None   # (p1,p2) de la última medición
        self.show_kerf =True   # dibujar trayectoria compensada real
        self._history  =[]    # pila de snapshots de all_segs (undo)
        self.custom_path=[]   # segmentos seleccionados manualmente en modo Path
        self.on_tool   =None  # callback(tool|mode) para resaltar botones
        self._open_cb  =None  # callback del botón "Abrir DXF" central
        self._empty_btn=None
        self._view     ={'ox':0.,'oy':0.,'scale':1.}
        self._drag0=None;self._view0=None

        self.bind('<Configure>',       lambda e:self._draw())
        self.bind('<ButtonPress-1>',   self._press)
        self.bind('<B1-Motion>',       self._drag)
        self.bind('<ButtonRelease-1>', lambda e:setattr(self,'_drag0',None))
        self.bind('<MouseWheel>',      self._wheel)
        self.bind('<Motion>',          self._motion)
        self.bind('<Escape>',          lambda e:self._cancel())
        self.bind('<ButtonPress-3>',   lambda e:self._cancel())

    # ── Carga ──────────────────────────────────────
    def load(self,segs,contours):
        self.all_segs=list(segs)
        self.contours=contours;self.active_idx=0;self.entry_seg=0;self.exit_seg=None
        self.thread_world=None;self.exit_world=None
        self.leadin_world=None;self.leadout_world=None
        self._tool='select';self._mode=None;self._draw_pts=[]
        self._history=[];self._info={};self.custom_path=[];self._measure=None
        if self.on_tool: self.on_tool('select')
        self.after(40,self._fit_active)

    # ── Undo ───────────────────────────────────────
    def _snapshot(self):
        """Guarda copia profunda de all_segs antes de un cambio."""
        self._history.append([dict(s) for s in self.all_segs])
        if len(self._history)>20: self._history.pop(0)

    def undo(self):
        if not self._history:
            if self.status_cb: self.status_cb('↩  Nada que deshacer')
            return
        self.all_segs=self._history.pop()
        self.contours=find_contours(self.all_segs)
        if self.active_idx>=len(self.contours): self.active_idx=max(0,len(self.contours)-1)
        self.entry_seg=0
        self._draw()
        if self.on_changed: self.on_changed()
        if self.status_cb: self.status_cb('↩  Deshecho')

    def active_chain(self):
        if self.custom_path: return self.custom_path
        if not self.contours: return []
        return rotate_chain(self.contours[self.active_idx],self.entry_seg)

    def update_info(self,info): self._info=info;self._draw()

    # ── Coords ─────────────────────────────────────
    def w2c(self,x,y):
        s=self._view['scale'];ox=self._view['ox'];oy=self._view['oy']
        return x*s+ox,-y*s+oy
    def c2w(self,cx,cy):
        s=self._view['scale'];ox=self._view['ox'];oy=self._view['oy']
        return (cx-ox)/s,-(cy-oy)/s

    def _snap(self,cx,cy):
        wx,wy=self.c2w(cx,cy);sr=SNAP_PX/self._view['scale']
        best_d=sr;best=(wx,wy)
        for seg in self.all_segs:
            for pt in [seg['start'],seg['end']]:
                d=pdist((wx,wy),pt)
                if d<best_d: best_d=d;best=pt
        return best

    def _snap_is_ep(self,pt):
        sr=SNAP_PX/self._view['scale']
        for seg in self.all_segs:
            for ep in [seg['start'],seg['end']]:
                if pdist(pt,ep)<sr: return True
        return False

    def _fit_active(self):
        chain=self.active_chain()
        if not chain: return
        xs=[];ys=[]
        for seg in chain:
            xs+=[seg['start'][0],seg['end'][0]];ys+=[seg['start'][1],seg['end'][1]]
            if seg['type']=='ARC':
                cx,cy,r=seg['cx'],seg['cy'],seg['r']
                xs+=[cx-r,cx+r];ys+=[cy-r,cy+r]
        W=self.winfo_width() or 500;H=self.winfo_height() or 400
        dx=max(xs)-min(xs) or 1;dy=max(ys)-min(ys) or 1
        s=min(W*.8/dx,H*.8/dy);self._view['scale']=s
        self._view['ox']=W/2-(min(xs)+max(xs))/2*s
        self._view['oy']=H/2+(min(ys)+max(ys))/2*s
        self._draw()

    def _rebuild(self):
        prev_len=_clen(self.contours[self.active_idx]) if self.contours else 0
        self.contours=find_contours(self.all_segs)
        if self.contours:
            best=0;best_d=float('inf')
            for i,c in enumerate(self.contours):
                d=abs(_clen(c)-prev_len)
                if d<best_d: best_d=d;best=i
            self.active_idx=min(best,len(self.contours)-1)
        self.entry_seg=0
        self._draw()
        if self.on_changed: self.on_changed()

    # ── Dibujo ─────────────────────────────────────
    def _draw(self):
        self.delete('all')
        W=self.winfo_width();H=self.winfo_height()
        self.create_rectangle(0,0,W,H,fill=CC['bg'],outline='')
        self._draw_grid()

        # Lienzo vacío → botón central "Abrir DXF"
        if not self.contours and not self.all_segs:
            self._draw_empty_button(W,H)
            self._draw_scale()
            return

        # Contornos de referencia
        for i,cont in enumerate(self.contours):
            if i==self.active_idx: continue
            col=CC['hover'] if i==self._hover_idx else CC['ref']
            for seg in cont:
                pts=self._pts(seg)
                if len(pts)>=4: self.create_line(pts,fill=col,width=1.5)

        # Contorno activo
        if not self.custom_path:
            chain=self.active_chain()
            n_chain=len(chain)
            exit_i=self.exit_seg if (self.exit_seg is not None and self.exit_seg<n_chain) else n_chain-1
            for i,seg in enumerate(chain):
                pts=self._pts(seg)
                if len(pts)<4: continue
                if i==0:             col=CC['entry']   # entrada — amarillo
                elif i==exit_i:      col=CC['exit']    # salida — naranja
                else:                col=CC['active']  # azul
                w=2.5 if i in (0,exit_i) else 2.0
                self.create_line(pts,fill=col,width=w)
            if chain:
                self._draw_arrow(chain[0])
                if exit_i!=0: self._draw_arrow(chain[exit_i])
        else:
            # — Fondo: mostrar TODOS los segmentos como referencia clickeable
            orig_in_path={id(s.get('_orig',s)) for s in self.custom_path}
            for seg in self.all_segs:
                if id(seg) in orig_in_path: continue   # ya está seleccionado
                pts=self._pts(seg)
                if len(pts)<4: continue
                self.create_line(pts,fill='#bdc1c6',width=1.5,dash=(4,3))

            # — Encima: segmentos seleccionados en violeta con número
            for i,seg in enumerate(self.custom_path):
                pts=self._pts(seg)
                if len(pts)<4: continue
                self.create_line(pts,fill='#6200ea',width=2.5)
                sx,sy=seg['start'];ex,ey=seg['end']
                mx,my=(sx+ex)/2,(sy+ey)/2
                px,py=self.w2c(mx,my)
                self.create_oval(px-10,py-10,px+10,py+10,fill='#ede7f6',outline='#6200ea',width=1.5)
                self.create_text(px,py,text=str(i+1),fill='#cba6f7',font=('SF Mono',9,'bold'))
                self._draw_arrow(seg)

            # Banner superior
            W2=self.winfo_width()
            self.create_rectangle(0,0,W2,26,fill='#ede7f6',outline='')
            self.create_line(0,26,W2,26,fill='#6200ea',width=1)
            n=len(self.custom_path)
            msg=(f'MODO PATH — {n} seg seleccionados  |  Clic = agregar  |  Clic sobre morado = quitar  |  ✔ Listo'
                 if n>0 else
                 'MODO PATH — Haz clic en los segmentos EN ORDEN que quieres cortar')
            self.create_text(W2//2,13,text=msg,fill='#6200ea',font=('SF Mono',9,'bold'))

        # Etiquetas de contorno (número + longitud)
        self._draw_contour_labels()

        # Info generado
        info=self._info
        if info:
            lx,ly=info['lx'],info['ly'];sx,sy=info['sx'],info['sy']
            tx,ty=info['tx'],info['ty']
            clx,cly=self.w2c(lx,ly);csx,csy=self.w2c(sx,sy);ctx,cty=self.w2c(tx,ty)
            self.create_line(ctx,cty,clx,cly,fill=CC['thread'],width=1.5,dash=(3,4))
            self.create_line(clx,cly,csx,csy,fill=CC['leadin'],width=2,dash=(6,3))
            self._arrowhead(clx,cly,csx,csy,CC['leadin'])
            self._dot(lx,ly,CC['leadin'],'LEAD-IN','e')
            ex_lx,ex_ly=info.get('ex_lx',lx),info.get('ex_ly',ly)
            if (ex_lx,ex_ly)!=(lx,ly):
                self._dot(ex_lx,ex_ly,CC['exit'],'SALIDA','w')

        # Kerf: trayectoria REAL del hilo compensada por el offset H1
        if info and self.show_kerf and info.get('kerf'):
            for kp in info['kerf']:
                if len(kp)<2: continue
                pts=[]
                for x,y in kp: pts+=list(self.w2c(x,y))
                self.create_line(pts,fill='#f9ab00',width=1.5,dash=(2,3))
        # Radios menores al offset → marcar riesgo de gouge
        if info:
            for gx,gy,_msg in info.get('gouges',[]):
                cx2,cy2=self.w2c(gx,gy)
                self.create_oval(cx2-9,cy2-9,cx2+9,cy2+9,outline='#d93025',width=2)
                self.create_text(cx2,cy2-16,text='⚠',fill='#d93025',
                                 font=('SF Pro Display',12,'bold'))

        if self.thread_world: self._dot(*self.thread_world,CC['thread'],'HILO','e')
        elif info and 'tx' in info: self._dot(info['tx'],info['ty'],CC['thread'],'HILO','e')
        if self.exit_world:    self._dot(*self.exit_world,  CC['exit'],'SALIDA','w')
        if self.leadin_world:  self._dot(*self.leadin_world,'#a6e3a1','LEAD-IN','e')
        if self.leadout_world: self._dot(*self.leadout_world,'#f38ba8','LEAD-OUT','w')

        # Medición persistente
        if self._measure:
            p1,p2=self._measure
            c1=self.w2c(*p1);c2=self.w2c(*p2)
            self.create_line(*c1,*c2,fill=CC['active'],width=1.5,dash=(4,3))
            for px,py in (c1,c2):
                self.create_line(px-4,py-4,px+4,py+4,fill=CC['active'],width=1.5)
                self.create_line(px-4,py+4,px+4,py-4,fill=CC['active'],width=1.5)
            dx=p2[0]-p1[0];dy=p2[1]-p1[1];d=math.hypot(dx,dy)
            mx,my=(c1[0]+c2[0])/2,(c1[1]+c2[1])/2
            txt=f'{d:.3f} mm'
            tw=len(txt)*7/2+8
            self.create_rectangle(mx-tw,my-24,mx+tw,my-8,fill='#e8f0fe',outline=CC['active'])
            self.create_text(mx,my-16,text=txt,fill=CC['active'],font=('SF Mono',9,'bold'))

        self._draw_tool_preview()

        # Snap indicator
        if self._hover_pt and self._tool in ('line','circle','arc','measure'):
            snapped=self._snap_is_ep(self._hover_pt)
            cx2,cy2=self.w2c(*self._hover_pt)
            col='#6200ea' if snapped else '#bdc1c6'
            self.create_oval(cx2-5,cy2-5,cx2+5,cy2+5,outline=col,width=1.5)

        if self._hover_pt:
            wx,wy=self._hover_pt
            self.create_text(W-6,H-8,anchor='se',
                text=f'X {wx:.3f}  Y {wy:.3f} mm',
                fill='#5f6368',font=('SF Mono',8))
        self._draw_scale()

    def _draw_empty_button(self,W,H):
        bw,bh=200,64;x0=W//2-bw//2;y0=H//2-bh//2
        self._empty_btn=(x0,y0,x0+bw,y0+bh)
        self.create_rectangle(x0,y0,x0+bw,y0+bh,fill=CC['active'],
                              outline='#1557b0',width=2)
        self.create_text(W//2,H//2,text='📂  Abrir DXF',
                         fill='white',font=('SF Pro Display',16,'bold'))
        self.create_text(W//2,y0+bh+22,
            text='o usa las herramientas de dibujo arriba',
            fill='#5f6368',font=('SF Pro Display',10))

    def _draw_contour_labels(self):
        for i,cont in enumerate(self.contours):
            if not cont: continue
            xs=[];ys=[]
            for seg in cont:
                xs+=[seg['start'][0],seg['end'][0]]
                ys+=[seg['start'][1],seg['end'][1]]
            if not xs: continue
            cx=sum(xs)/len(xs);cy=sum(ys)/len(ys)
            length=_clen(cont)
            px,py=self.w2c(cx,cy)
            col=CC['entry'] if i==self.active_idx else '#7f849c'
            self.create_text(px,py,text=f'{i+1} — {length:.0f}mm',
                             fill=col,font=('SF Mono',9,'bold'))

    def _draw_tool_preview(self):
        if not self._draw_pts and not self._hover_pt: return
        pts_w=self._draw_pts;hp=self._hover_pt or (0,0)
        tool=self._tool

        if tool=='line' and len(pts_w)==1:
            p1c=self.w2c(*pts_w[0]);p2c=self.w2c(*hp)
            self.create_line(*p1c,*p2c,fill=CC['user'],width=2,dash=(6,3))
            self._dot(*pts_w[0],CC['user'],'P1','e',sz=5)

        elif tool=='measure' and len(pts_w)==1:
            p1c=self.w2c(*pts_w[0]);p2c=self.w2c(*hp)
            self.create_line(*p1c,*p2c,fill=CC['active'],width=1.5,dash=(4,3))
            d=pdist(pts_w[0],hp)
            mx,my=(p1c[0]+p2c[0])/2,(p1c[1]+p2c[1])/2
            self.create_text(mx,my-10,text=f'{d:.3f} mm',
                             fill=CC['active'],font=('SF Mono',9,'bold'))
            self._dot(*pts_w[0],CC['active'],'P1','e',sz=5)

        elif tool=='circle' and len(pts_w)==1:
            cx2,cy2=pts_w[0];r=pdist((cx2,cy2),hp)
            if r>1e-6:
                p1c=self.w2c(cx2-r,cy2-r);p2c=self.w2c(cx2+r,cy2+r)
                self.create_oval(*p1c,*p2c,outline=CC['user'],width=2,dash=(6,3))
            self._dot(*pts_w[0],CC['user'],'CENTRO','e',sz=5)

        elif tool=='arc':
            if len(pts_w)>=1: self._dot(*pts_w[0],CC['user'],'C','e',sz=5)
            if len(pts_w)==1:
                r=pdist(pts_w[0],hp)
                if r>1e-6:
                    cx2,cy2=pts_w[0]
                    p1c=self.w2c(cx2-r,cy2-r);p2c=self.w2c(cx2+r,cy2+r)
                    self.create_oval(*p1c,*p2c,outline=CC['preview'],width=1,dash=(2,4))
            elif len(pts_w)==2:
                cx2,cy2=pts_w[0];r=pdist(pts_w[0],pts_w[1])
                sa=norm_d(math.degrees(math.atan2(pts_w[1][1]-cy2,pts_w[1][0]-cx2)))
                ea=norm_d(math.degrees(math.atan2(hp[1]-cy2,hp[0]-cx2)))
                span=(ea-sa)%360 or 360;n=max(6,int(span/4))
                cpts=[]
                for i in range(n+1):
                    a=sa+span*i/n
                    wx2=cx2+r*math.cos(math.radians(a));wy2=cy2+r*math.sin(math.radians(a))
                    px2,py2=self.w2c(wx2,wy2);cpts+=[px2,py2]
                if len(cpts)>=4:
                    self.create_line(cpts,fill=CC['user'],width=2,dash=(6,3))
                self._dot(*pts_w[1],CC['user'],'INICIO','e',sz=5)

    def _status_text(self):
        """Texto de la barra de estado según herramienta + estado actual."""
        np=len(self._draw_pts)
        if self._mode=='thread': return '📍  Clic en el agujero del hilo'
        if self._mode=='entry':  return '🎯  Clic en el punto de ENTRADA al contorno'
        if self._mode=='exit':   return '📤  Clic en el punto de SALIDA del contorno'
        if self._mode=='leadin':  return '➡  Clic en el punto de LEAD-IN (donde llega el hilo antes de entrar al corte)'
        if self._mode=='leadout': return '⬅  Clic en el punto de LEAD-OUT (donde sale el hilo después del corte)'
        if self._tool=='line':
            return '📏  Clic para segundo punto — ESC cancela' if np>=1 else '📏  Clic para primer punto'
        if self._tool=='circle':
            return '⭕  Clic en el borde — ESC cancela' if np>=1 else '⭕  Clic en el centro'
        if self._tool=='arc':
            if np>=2: return '🌙  Clic en el punto FINAL — ESC cancela'
            if np==1: return '🌙  Clic en el punto INICIAL'
            return '🌙  Clic en el centro'
        if self._tool=='measure':
            return '📐  Clic en el SEGUNDO punto — ESC sale' if np>=1 else '📐  Clic en el PRIMER punto a medir (snap a extremos)'
        if self._tool=='delete':
            return '🗑  Clic cerca de un segmento para borrarlo — ESC sale'
        if self._tool=='path':
            n=len(self.custom_path)
            if n==0: return '🛤  Clic en el PRIMER segmento del recorrido — ESC sale'
            return f'🛤  Segmento {n} agregado — clic en el SIGUIENTE  |  Doble-clic o botón ✅ para terminar'
        return None

    def _draw_arrow(self,seg):
        sx,sy=seg['start'];ex,ey=seg['end']
        mx,my=(sx+ex)/2,(sy+ey)/2;tx,ty=seg_tangent(seg)
        aw=4./self._view['scale']
        b=self.w2c(mx,my);t2=self.w2c(mx+tx*aw*3,my+ty*aw*3)
        self.create_line(*b,*t2,fill='#cba6f7',width=2,arrow='last',arrowshape=(8,10,4))

    def _arrowhead(self,x1,y1,x2,y2,color):
        dx=x2-x1;dy=y2-y1;d=math.hypot(dx,dy)
        if d<1e-9: return
        ux=dx/d;uy=dy/d
        self.create_polygon(x2,y2,x2-ux*10+uy*5,y2-uy*10-ux*5,
                             x2-ux*10-uy*5,y2-uy*10+ux*5,fill=color,outline='')

    def _dot(self,wx,wy,color,label='',anchor='w',sz=6):
        cx,cy=self.w2c(wx,wy)
        self.create_oval(cx-sz,cy-sz,cx+sz,cy+sz,fill=color,outline='white',width=1.5)
        if label:
            off=sz+4;tx=cx+off if anchor=='e' else cx-off
            self.create_text(tx,cy,text=label,fill=color,font=('SF Mono',8),anchor=anchor)

    def _pts(self,seg):
        t=seg['type']
        if t=='LINE':
            p1=self.w2c(*seg['start']);p2=self.w2c(*seg['end'])
            return [p1[0],p1[1],p2[0],p2[1]]
        elif t=='ARC':
            cx,cy,r=seg['cx'],seg['cy'],seg['r']
            sa,ea,ccw=seg['sa'],seg['ea'],seg.get('ccw',True)
            span=(ea-sa)%360 if ccw else -((sa-ea)%360)
            if abs(span)<1e-6: span=360. if ccw else -360.
            n=max(12,int(abs(span)/3));pts=[]
            for i in range(n+1):
                a=sa+span*i/n
                wx=cx+r*math.cos(math.radians(a));wy=cy+r*math.sin(math.radians(a))
                px,py=self.w2c(wx,wy);pts+=[px,py]
            return pts
        return []

    def _draw_grid(self):
        W=self.winfo_width();H=self.winfo_height();s=self._view['scale']
        for sp in [.1,.5,1,2,5,10,20,50,100,200,500]:
            if sp*s>40: break
        sp=max(sp,.01)
        x0w,_=self.c2w(0,0);x1w,_=self.c2w(W,0)
        _,y0w=self.c2w(0,0);_,y1w=self.c2w(0,H)
        gx=math.floor(min(x0w,x1w)/sp)*sp;gy=math.floor(min(y0w,y1w)/sp)*sp
        x=gx
        while x<=max(x0w,x1w)+sp:
            cx2,_=self.w2c(x,0);self.create_line(cx2,0,cx2,H,fill='#e8eaed',width=1);x+=sp
        y=gy
        while y<=max(y0w,y1w)+sp:
            _,cy2=self.w2c(0,y);self.create_line(0,cy2,W,cy2,fill='#e8eaed',width=1);y+=sp

    def _draw_scale(self):
        W=self.winfo_width();H=self.winfo_height();s=self._view['scale']
        for bm in [.1,.5,1,2,5,10,20,50,100,200,500]:
            if bm*s>80: break
        bp=bm*s;x0,y0=14,H-14
        self.create_line(x0,y0,x0+bp,y0,fill='#5f6368',width=2)
        for xp in [x0,x0+bp]: self.create_line(xp,y0-4,xp,y0+4,fill='#5f6368',width=2)
        lbl=f'{bm}mm' if bm>=1 else f'{bm*1000:.0f}µm'
        self.create_text(x0+bp/2,y0-10,text=lbl,fill='#5f6368',font=('SF Mono',8))

    # ── Herramientas ───────────────────────────────
    def _emit_status(self):
        if self.status_cb:
            t=self._status_text()
            if t: self.status_cb(t)

    def set_tool(self,tool):
        self._tool=tool;self._mode=None;self._draw_pts=[]
        if tool!='measure': self._measure=None
        self.config(cursor='crosshair' if tool!='select' else '')
        if self.on_tool: self.on_tool(tool)
        self._emit_status();self._draw()

    def set_mode(self,mode):
        self._mode=mode;self._tool='select';self._draw_pts=[]
        self.config(cursor='crosshair')
        if self.on_tool: self.on_tool(mode)
        self._emit_status();self._draw()

    def _cancel(self):
        self._tool='select';self._mode=None;self._draw_pts=[];self._measure=None
        self.config(cursor='')
        if self.on_tool: self.on_tool('select')
        if self.status_cb: self.status_cb('🖱  Modo selección')
        self._draw()

    def _motion(self,ev):
        if self._tool!='select' or self._mode:
            self._hover_pt=self._snap(ev.x,ev.y)
            self._draw();return
        self._hover_pt=self.c2w(ev.x,ev.y)
        if len(self.contours)>1:
            wx,wy=self.c2w(ev.x,ev.y);best_d=float('inf');best_i=0
            for i,c in enumerate(self.contours):
                for seg in c:
                    d=seg_dist(seg,wx,wy)
                    if d<best_d: best_d=d;best_i=i
            if best_i!=self._hover_idx: self._hover_idx=best_i;self._draw()

    def _press(self,ev):
        # Botón "Abrir DXF" en lienzo vacío
        if not self.contours and not self.all_segs and self._open_cb:
            b=getattr(self,'_empty_btn',None)
            if b and b[0]<=ev.x<=b[2] and b[1]<=ev.y<=b[3]:
                self._open_cb();return
        if self._mode:          self._handle_mode(ev.x,ev.y); return
        if self._tool=='delete':self._do_delete(ev.x,ev.y); return
        if self._tool=='path':  self._do_path_click(ev.x,ev.y); return
        if self._tool=='measure':self._do_measure(ev.x,ev.y); return
        if self._tool=='select':
            if len(self.contours)>1:
                wx,wy=self.c2w(ev.x,ev.y);best_d=float('inf');best_i=0
                for i,c in enumerate(self.contours):
                    for seg in c:
                        d=seg_dist(seg,wx,wy)
                        if d<best_d: best_d=d;best_i=i
                if best_i!=self.active_idx:
                    self.active_idx=best_i;self.entry_seg=0
                    self._fit_active()
                    if self.on_changed: self.on_changed();return
            self._drag0=(ev.x,ev.y);self._view0=(self._view['ox'],self._view['oy'])
        elif self._tool in ('line','circle','arc'):
            self._do_draw(ev.x,ev.y)

    def _handle_mode(self,cx,cy):
        mode=self._mode;self._mode=None;self.config(cursor='')
        if self.on_tool: self.on_tool('select')
        wx,wy=self.c2w(cx,cy)

        if mode=='thread':
            self.thread_world=self._snap(cx,cy)
            if self.status_cb: self.status_cb('● Hilo fijado')
        elif mode=='leadin':
            self.leadin_world=self._snap(cx,cy)
            if self.status_cb: self.status_cb(f'→ Lead-in fijado en ({self.leadin_world[0]:.2f}, {self.leadin_world[1]:.2f}) mm')
        elif mode=='leadout':
            self.leadout_world=self._snap(cx,cy)
            if self.status_cb: self.status_cb(f'← Lead-out fijado en ({self.leadout_world[0]:.2f}, {self.leadout_world[1]:.2f}) mm')
        elif mode=='entry':
            # Snap al endpoint más cercano del contorno. Si el punto clickeado
            # es el FINAL de un segmento, la entrada real es el segmento
            # SIGUIENTE (que empieza ahí) — así el corte arranca donde se hizo clic.
            chain=self.contours[self.active_idx] if self.contours else []
            n=len(chain);best_d=float('inf');best_i=0
            for i,seg in enumerate(chain):
                d=pdist((wx,wy),seg['start'])
                if d<best_d: best_d=d;best_i=i
                d=pdist((wx,wy),seg['end'])
                if d<best_d: best_d=d;best_i=(i+1)%n
            self.entry_seg=best_i
            ep=chain[best_i]['start'] if chain else (0,0)
            if self.status_cb: self.status_cb(f'▷ Entrada: segmento {best_i+1} — ({ep[0]:.2f},{ep[1]:.2f}) mm')
        elif mode=='exit':
            # Snap al segmento más cercano del contorno (igual que entrada)
            chain=self.contours[self.active_idx] if self.contours else []
            best_d=float('inf');best_i=len(chain)-1
            for i,seg in enumerate(chain):
                d=seg_dist(seg,wx,wy)
                if d<best_d: best_d=d;best_i=i
            self.exit_seg=best_i
            self.exit_world=None   # ya no usamos el punto libre
            ep=chain[best_i]['end'] if chain else (0,0)
            if self.status_cb: self.status_cb(f'◁ Salida: segmento {best_i+1} — lead-out perpendicular en ({ep[0]:.2f},{ep[1]:.2f}) mm')

        if self.on_changed: self.on_changed()
        self._draw()

    # ── Línea / Círculo / Arco (quedan activos) ────
    def _do_draw(self,cx,cy):
        wp=self._snap(cx,cy);self._draw_pts.append(wp)
        tool=self._tool;pts=self._draw_pts;committed=False

        if tool=='line' and len(pts)==2:
            p1,p2=pts
            if pdist(p1,p2)>0.01:
                self._snapshot()
                self.all_segs.append({'type':'LINE','start':p1,'end':p2})
                committed=True
            self._draw_pts=[]

        elif tool=='circle' and len(pts)==2:
            cx2,cy2=pts[0];r=pdist(pts[0],pts[1])
            if r>0.01:
                self._snapshot()
                self.all_segs.append({'type':'ARC','cx':cx2,'cy':cy2,'r':r,
                    'sa':0.,'ea':180.,'ccw':True,
                    'start':ang(cx2,cy2,r,0.),'end':ang(cx2,cy2,r,180.)})
                self.all_segs.append({'type':'ARC','cx':cx2,'cy':cy2,'r':r,
                    'sa':180.,'ea':0.,'ccw':True,
                    'start':ang(cx2,cy2,r,180.),'end':ang(cx2,cy2,r,0.)})
                committed=True
            self._draw_pts=[]

        elif tool=='arc' and len(pts)==3:
            c_pt,s_pt,e_pt=pts;cx2,cy2=c_pt;r=pdist(c_pt,s_pt)
            if r>0.01:
                sa=norm_d(math.degrees(math.atan2(s_pt[1]-cy2,s_pt[0]-cx2)))
                ea=norm_d(math.degrees(math.atan2(e_pt[1]-cy2,e_pt[0]-cx2)))
                sx2,sy2=ang(cx2,cy2,r,sa);ex2,ey2=ang(cx2,cy2,r,ea)
                self._snapshot()
                self.all_segs.append({'type':'ARC','cx':cx2,'cy':cy2,'r':r,
                    'sa':sa,'ea':ea,'ccw':True,'start':(sx2,sy2),'end':(ex2,ey2)})
                committed=True
            self._draw_pts=[]

        if committed:
            self._rebuild()   # reconstruye contornos; la herramienta sigue activa
        # Siempre actualizar prompt y vista (herramienta permanece activa)
        self._emit_status()
        self._draw()

    # ── Borrar = eliminar el segmento más cercano ──
    def _nearest_seg_idx(self,wx,wy):
        best_d=float('inf');best_i=None
        for i,seg in enumerate(self.all_segs):
            d=seg_dist(seg,wx,wy)
            if d<best_d: best_d=d;best_i=i
        return best_i

    def _do_delete(self,cx,cy):
        wx,wy=self.c2w(cx,cy)
        idx=self._nearest_seg_idx(wx,wy)
        if idx is None:
            if self.status_cb: self.status_cb('🗑  No hay segmentos para borrar')
            return
        # Sólo borrar si el clic está razonablemente cerca del segmento
        if seg_dist(self.all_segs[idx],wx,wy)>20/self._view['scale']:
            if self.status_cb: self.status_cb('🗑  Acércate más a un segmento — ESC sale')
            return
        self._snapshot()
        self.all_segs.pop(idx)
        self._rebuild()   # reconstruye contornos; la herramienta sigue activa
        if self.status_cb:
            self.status_cb(f'🗑  Segmento borrado ({len(self.all_segs)} restantes) — ESC sale')

    # ── Medir — distancia entre dos puntos ──
    def _do_measure(self,cx,cy):
        wp=self._snap(cx,cy)
        self._draw_pts.append(wp)
        if len(self._draw_pts)==2:
            p1,p2=self._draw_pts
            self._measure=(p1,p2)
            self._draw_pts=[]
            dx=p2[0]-p1[0];dy=p2[1]-p1[1];d=math.hypot(dx,dy)
            a=math.degrees(math.atan2(dy,dx))%360
            if self.status_cb:
                self.status_cb(f'📐  Dist {d:.3f} mm   ΔX {dx:+.3f}   ΔY {dy:+.3f}   ∠ {a:.1f}°')
        else:
            self._emit_status()
        self._draw()

    # ── Path manual — seleccionar segmentos en orden ──
    @staticmethod
    def _seg_reversed(seg):
        """Devuelve copia del segmento con dirección invertida."""
        s=dict(seg)
        s['start'],s['end']=seg['end'],seg['start']
        if seg['type']=='ARC': s['ccw']=not seg['ccw']
        return s

    def _do_path_click(self,cx,cy):
        wx,wy=self.c2w(cx,cy)
        # Buscar el segmento original más cercano
        best_d=float('inf');best_seg=None;best_orig=None
        for seg in self.all_segs:
            d=seg_dist(seg,wx,wy)
            if d<best_d: best_d=d;best_orig=seg
        if best_orig is None or best_d>30/self._view['scale']:
            if self.status_cb: self.status_cb('🛤  Acércate más a un segmento')
            return

        # Toggle: si el original ya está en el path (por referencia al orig), quitarlo
        for i,s in enumerate(self.custom_path):
            if s.get('_orig') is best_orig:
                self.custom_path.pop(i)
                if self.status_cb: self.status_cb(f'🛤  Segmento {i+1} eliminado')
                self._emit_status();self._draw()
                if self.on_changed: self.on_changed()
                return

        # Auto-orientar respecto al último segmento del path
        if self.custom_path:
            prev_end=self.custom_path[-1]['end']
            d_start=pdist(prev_end, best_orig['start'])
            d_end  =pdist(prev_end, best_orig['end'])
            if d_end < d_start:          # el end del orig está más cerca → invertir
                seg=self._seg_reversed(best_orig)
            else:
                seg=dict(best_orig)
        else:
            # Primer segmento: orientar según el lado del canvas donde hizo clic
            # (lado más cercano al clic = start)
            d_start=pdist((wx,wy), best_orig['start'])
            d_end  =pdist((wx,wy), best_orig['end'])
            seg=dict(best_orig) if d_start<=d_end else self._seg_reversed(best_orig)

        seg['_orig']=best_orig   # referencia al original para poder quitarlo
        self.custom_path.append(seg)
        self._emit_status();self._draw()
        if self.on_changed: self.on_changed()

    def clear_path(self):
        self.custom_path=[]
        self._tool='select';self.config(cursor='')
        if self.on_tool: self.on_tool('select')
        self._emit_status();self._draw()
        if self.on_changed: self.on_changed()
        if self.status_cb: self.status_cb('🛤  Path limpiado — volviendo a modo automático')

    def _drag(self,ev):
        if self._drag0 and self._tool=='select' and not self._mode:
            dx=ev.x-self._drag0[0];dy=ev.y-self._drag0[1]
            self._view['ox']=self._view0[0]+dx;self._view['oy']=self._view0[1]+dy;self._draw()

    def _wheel(self,ev):
        f=1.12 if ev.delta>0 else 0.9;wx,wy=self.c2w(ev.x,ev.y)
        self._view['scale']*=f;self._view['ox']=ev.x-wx*self._view['scale']
        self._view['oy']=ev.y+wy*self._view['scale'];self._draw()

# ═══════════════════════════════════════════════════
#  APP  —  Tema claro
# ═══════════════════════════════════════════════════
DARK  ='#f8f9fa'   # fondo app
PANEL ='#ffffff'   # paneles blancos
SIDEBAR='#f1f3f4'  # sidebar gris claro
ACCENT='#1967d2'   # azul Google
ACCENT2='#e8f0fe'  # azul claro (hover)
TEXT  ='#202124'   # texto oscuro
TEXT2 ='#5f6368'   # texto secundario
ENTRY ='#ffffff'   # bg entrada
BORDER='#dadce0'   # bordes
GREEN ='#1e7e34'   # verde éxito
YELLOW='#e37400'   # ámbar
BLUE  ='#1a73e8'   # azul info
RED   ='#d93025'   # rojo error
SEL   ='#e8f0fe'   # selección

E_SKIM=[
    {'w_sp':4,'i_max':1,'pul_on':24,'p_ratio':3,'voltage':100,'aux':0,'speed':9},
    {'w_sp':4,'i_max':1,'pul_on':18,'p_ratio':3,'voltage': 90,'aux':0,'speed':6},
    {'w_sp':3,'i_max':1,'pul_on':14,'p_ratio':3,'voltage': 80,'aux':0,'speed':4},
    {'w_sp':2,'i_max':1,'pul_on':10,'p_ratio':2,'voltage': 70,'aux':0,'speed':3},
]
H_DEF=[100,75,60,50]

# ── Presets de material (persisten en el home del usuario) ──
PRESET_FILE=os.path.expanduser('~/.wedm_presets.json')
def load_presets():
    try:
        with open(PRESET_FILE,encoding='utf-8') as f: return json.load(f)
    except Exception: return {}
def save_presets(d):
    try:
        with open(PRESET_FILE,'w',encoding='utf-8') as f: json.dump(d,f,indent=1,ensure_ascii=False)
    except Exception: pass

class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(f'Wire EDM Post-Processor  —  SKD2 / EAPT  v{__version__}')
        self.configure(bg=DARK);self.geometry('1350x820');self.minsize(960,640)
        self._code='';self._units='mm'
        self.v_dxf=tk.StringVar();self.v_layer=tk.StringVar()
        self.v_mode=tk.StringVar(value='Core');self.v_cutin=tk.StringVar(value='perp')
        self.v_comp=tk.StringVar(value='auto');self.v_cuts=tk.IntVar(value=1)
        self.v_mat=tk.StringVar(value='SKD11');self.v_thick=tk.StringVar(value='10')
        self.v_wire=tk.StringVar(value='0.18');self.v_flush=tk.StringVar(value='DIC206')
        self.v_leadin=tk.StringVar(value='3.0');self.v_overcut=tk.StringVar(value='0.0')
        self.v_cutspeed=tk.StringVar(value='2.0')   # mm/min primera pasada (estimación)
        self.v_kerf=tk.BooleanVar(value=True)       # mostrar trayectoria compensada
        self.v_leadin_angle =tk.StringVar(value='')   # ángulo lead-in  (vacío = auto/perp)
        self.v_leadout_angle=tk.StringVar(value='')   # ángulo lead-out (vacío = auto/perp)
        self.v_same_lead=tk.BooleanVar(value=False)
        self.v_force_exit=tk.BooleanVar(value=False)
        self.v_rotate=tk.StringVar(value='0')
        self.h_vars=[tk.StringVar(value=str(H_DEF[i])) for i in range(4)]
        self.e_keys=['w_sp','i_max','pul_on','p_ratio','voltage','aux','speed']
        # 4 cuts × 7 params — each cut has its own editable row
        self.e_vars=[[tk.StringVar(value=str(E_SKIM[i][k])) for k in self.e_keys]
                     for i in range(4)]
        self._build()
        self.v_cuts.trace_add('write',lambda *_:self._refresh_h())

    def _build(self):
        self.configure(bg=DARK)
        # ── Header ─────────────────────────────────────────
        hdr=tk.Frame(self,bg=ACCENT,height=52);hdr.pack(fill='x');hdr.pack_propagate(False)
        tk.Label(hdr,text='⚡ Wire EDM',bg=ACCENT,fg='white',
                 font=('SF Pro Display',16,'bold'),padx=16).pack(side='left',pady=12)
        tk.Label(hdr,text='Post-Processor  ·  SKD2 / EAPT',bg=ACCENT,fg='#aec8f8',
                 font=('SF Pro Display',11)).pack(side='left')
        self.lbl_units=tk.Label(hdr,text='',bg=ACCENT,fg='#aec8f8',
                                font=('SF Pro Display',9),padx=12)
        self.lbl_units.pack(side='right')
        tk.Label(hdr,text=f'v{__version__}  ·  by Arturo Rebolledo',bg=ACCENT,fg='#aec8f8',
                 font=('SF Pro Display',9),padx=8).pack(side='right')

        # ── Body ────────────────────────────────────────────
        body=tk.Frame(self,bg=DARK);body.pack(fill='both',expand=True)

        left=tk.Frame(body,bg=SIDEBAR,width=270);left.pack(side='left',fill='y')
        left.pack_propagate(False)
        # borde derecho del sidebar
        tk.Frame(body,bg=BORDER,width=1).pack(side='left',fill='y')
        self._build_params(left)

        mid=tk.Frame(body,bg=DARK);mid.pack(side='left',fill='both',expand=True)
        self._build_canvas(mid)

        tk.Frame(body,bg=BORDER,width=1).pack(side='left',fill='y')
        right=tk.Frame(body,bg=PANEL,width=320);right.pack(side='left',fill='both',expand=True)
        right.pack_propagate(False)
        self._build_code(right)

        # ── Barra de estado ────────────────────────────────
        bar=tk.Frame(self,bg=PANEL,height=42);bar.pack(fill='x');bar.pack_propagate(False)
        tk.Frame(bar,bg=BORDER,height=1).pack(fill='x',side='top')
        self.lbl_st=tk.Label(bar,text='Carga un DXF o dibuja el perfil.',
                              bg=PANEL,fg=TEXT2,font=('SF Pro Display',9),padx=12)
        self.lbl_st.pack(side='left',pady=8)
        # Botones acción principales
        def abtn(txt,cmd,bg,fg='white'):
            tk.Button(bar,text=txt,command=cmd,bg=bg,fg=fg,relief='flat',
                      font=('SF Pro Display',10,'bold'),padx=14,pady=5,cursor='hand2',
                      activebackground=bg,activeforeground=fg
                      ).pack(side='right',padx=(0,8),pady=6)
        abtn('💾  Guardar .ISO', self._save,    ACCENT)
        abtn('⧉  TODO',          self._gen_all, '#6200ea')
        abtn('▶  Generar',       self._gen,     '#1e7e34')
        abtn('▶  Simular',       self._simulate,'#c62828')

    def _build_params(self,p):
        # Scrollbar visible con botones de flecha arriba/abajo
        nav=tk.Frame(p,bg=SIDEBAR);nav.pack(side='bottom',fill='x')
        tk.Button(nav,text='▲',command=lambda:cv.yview_scroll(-3,'units'),
                  bg=BORDER,fg=TEXT,relief='flat',font=('SF Pro Display',11),
                  cursor='hand2',pady=2).pack(side='left',fill='x',expand=True)
        tk.Button(nav,text='▼',command=lambda:cv.yview_scroll(3,'units'),
                  bg=BORDER,fg=TEXT,relief='flat',font=('SF Pro Display',11),
                  cursor='hand2',pady=2).pack(side='left',fill='x',expand=True)

        sb=tk.Scrollbar(p,orient='vertical',width=16,
                        bg='#dadce0',troughcolor=SIDEBAR,
                        activebackground=ACCENT,relief='flat',bd=0)
        sb.pack(side='right',fill='y')
        cv=tk.Canvas(p,bg=SIDEBAR,highlightthickness=0,yscrollcommand=sb.set)
        sb.config(command=cv.yview)
        f=tk.Frame(cv,bg=SIDEBAR)
        cv.create_window((0,0),window=f,anchor='nw',width=240)
        cv.pack(side='left',fill='both',expand=True)

        f.bind('<Configure>', lambda e: cv.configure(scrollregion=cv.bbox('all')))

        def sec(t):
            tk.Frame(f,bg=BORDER,height=1).pack(fill='x',padx=0,pady=(10,0))
            tk.Label(f,text=t,bg=SIDEBAR,fg=ACCENT,font=('SF Pro Display',9,'bold')
                     ).pack(anchor='w',pady=(4,3),padx=10)
        def row(lbl,var,choices=None,w=10):
            rf=tk.Frame(f,bg=SIDEBAR);rf.pack(fill='x',padx=10,pady=2)
            tk.Label(rf,text=lbl,bg=SIDEBAR,fg=TEXT,font=('SF Pro Display',9),
                     width=11,anchor='w').pack(side='left')
            if choices:
                style=ttk.Style();style.configure('Light.TCombobox',fieldbackground=ENTRY,
                                                   background=ENTRY,foreground=TEXT)
                cb=ttk.Combobox(rf,textvariable=var,values=choices,width=w-2,state='readonly')
                cb.pack(side='left');return cb
            e=tk.Entry(rf,textvariable=var,bg=ENTRY,fg=TEXT,insertbackground=TEXT,
                       relief='solid',bd=1,font=('SF Mono',9),width=w,
                       highlightthickness=1,highlightbackground=BORDER,highlightcolor=ACCENT)
            e.pack(side='left');return e

        # Botón DXF prominente
        tk.Frame(f,bg=SIDEBAR,height=8).pack()
        tk.Button(f,text='📂  Abrir DXF…',command=self._open,bg=ACCENT,fg='white',
                  relief='flat',font=('SF Pro Display',10,'bold'),padx=10,pady=7,
                  cursor='hand2',width=22).pack(padx=10,pady=(0,2),fill='x')
        fr=tk.Frame(f,bg=SIDEBAR);fr.pack(fill='x',padx=10,pady=(0,4))
        tk.Entry(fr,textvariable=self.v_dxf,bg=ENTRY,fg=TEXT2,insertbackground=TEXT,
                 relief='solid',bd=1,font=('SF Mono',7),width=18).pack(side='left')
        row('Layer',self.v_layer,w=9)

        sec('⚙  PROCESO')
        row('Modo',   self.v_mode,  choices=['Core','Cavity'])
        row('Cutin',  self.v_cutin, choices=['perp','line','point'])
        row('Comp',   self.v_comp,  choices=['auto','G41','G42'])
        row('Pasadas',self.v_cuts,  choices=[1,2,3,4],w=5)
        rfk=tk.Frame(f,bg=SIDEBAR);rfk.pack(fill='x',padx=10,pady=(2,2))
        tk.Checkbutton(rfk,text='Ver kerf (trayectoria real)',
                       variable=self.v_kerf,bg=SIDEBAR,fg='#b45309',
                       selectcolor=ENTRY,activebackground=SIDEBAR,activeforeground='#b45309',
                       font=('SF Pro Display',9),command=self._toggle_kerf
                       ).pack(anchor='w')

        sec('🔩  MATERIAL')
        row('Material',  self.v_mat)
        row('Espesor mm',self.v_thick,w=7)
        row('Hilo Ø mm', self.v_wire, w=7)
        row('Flush',     self.v_flush)
        row('Vel mm/min',self.v_cutspeed,w=7)
        tk.Label(f,text='Vel. de corte 1ª pasada — para estimar tiempo',
                 bg=SIDEBAR,fg=TEXT2,font=('SF Pro Display',7)).pack(anchor='w',padx=14)

        sec('💾  PRESETS')
        self.v_preset=tk.StringVar()
        prf=tk.Frame(f,bg=SIDEBAR);prf.pack(fill='x',padx=10,pady=2)
        self._preset_cb=ttk.Combobox(prf,textvariable=self.v_preset,values=[],
                                     width=24,state='readonly')
        self._preset_cb.pack(fill='x')
        self._preset_cb.bind('<<ComboboxSelected>>',self._preset_load)
        prb=tk.Frame(f,bg=SIDEBAR);prb.pack(fill='x',padx=10,pady=(3,2))
        tk.Button(prb,text='💾 Guardar preset',command=self._preset_save,
                  bg=ACCENT,fg='white',relief='flat',font=('SF Pro Display',9,'bold'),
                  padx=6,pady=3,cursor='hand2').pack(side='left',fill='x',expand=True)
        tk.Button(prb,text='🗑',command=self._preset_delete,
                  bg='#fce8e6',fg=RED,relief='flat',font=('SF Pro Display',9,'bold'),
                  padx=8,pady=3,cursor='hand2').pack(side='left',padx=(4,0))
        self._preset_refresh()

        sec('📐  LEAD-IN / OUT')
        row('Lead-in mm', self.v_leadin,  w=7)
        row('Overcut mm', self.v_overcut, w=7)

        # Lead-in por ángulo + distancia
        tk.Frame(f,bg=BORDER,height=1).pack(fill='x',padx=10,pady=(6,0))
        tk.Label(f,text='Lead-in por ángulo',bg=SIDEBAR,fg=ACCENT,
                 font=('SF Pro Display',8,'bold')).pack(anchor='w',padx=10,pady=(4,1))
        row('Ángulo °', self.v_leadin_angle, w=7)
        tk.Label(f,text='0°=→  90°=↑  180°=←  270°=↓',
                 bg=SIDEBAR,fg=TEXT2,font=('SF Pro Display',7)).pack(anchor='w',padx=14)
        rf_apply=tk.Frame(f,bg=SIDEBAR);rf_apply.pack(fill='x',padx=10,pady=(3,2))
        tk.Button(rf_apply,text='⟳ Aplicar Lead-in',command=self._apply_leadin_angle,
                  bg=GREEN,fg='white',relief='flat',font=('SF Pro Display',9,'bold'),
                  padx=8,pady=4,cursor='hand2').pack(fill='x')

        # Lead-out por ángulo
        tk.Frame(f,bg=BORDER,height=1).pack(fill='x',padx=10,pady=(6,0))
        tk.Label(f,text='Lead-out por ángulo',bg=SIDEBAR,fg=ACCENT,
                 font=('SF Pro Display',8,'bold')).pack(anchor='w',padx=10,pady=(4,1))
        row('Ángulo °', self.v_leadout_angle, w=7)
        rf_apply2=tk.Frame(f,bg=SIDEBAR);rf_apply2.pack(fill='x',padx=10,pady=(3,2))
        tk.Button(rf_apply2,text='⟳ Aplicar Lead-out',command=self._apply_leadout_angle,
                  bg='#6200ea',fg='white',relief='flat',font=('SF Pro Display',9,'bold'),
                  padx=8,pady=4,cursor='hand2').pack(fill='x')

        rf3=tk.Frame(f,bg=SIDEBAR);rf3.pack(fill='x',padx=10,pady=(6,2))
        tk.Checkbutton(rf3,text='Lead-out = Lead-in (mismo punto)',
                       variable=self.v_same_lead,bg=SIDEBAR,fg=GREEN,
                       selectcolor=ENTRY,activebackground=SIDEBAR,activeforeground=GREEN,
                       font=('SF Pro Display',9),command=self._gen
                       ).pack(anchor='w')
        rf4=tk.Frame(f,bg=SIDEBAR);rf4.pack(fill='x',padx=10,pady=(2,4))
        tk.Checkbutton(rf4,text='Salida forzada G00 (pieza que cae)',
                       variable=self.v_force_exit,bg=SIDEBAR,fg=RED,
                       selectcolor=ENTRY,activebackground=SIDEBAR,activeforeground=RED,
                       font=('SF Pro Display',9),command=self._gen
                       ).pack(anchor='w')

        sec('📏  OFFSET H (µm)')
        self._h_rows=[]
        for i in range(4):
            rf=tk.Frame(f,bg=SIDEBAR);rf.pack(fill='x',padx=10,pady=2)
            tk.Label(rf,text=f'  Cut {i+1}',bg=SIDEBAR,fg=TEXT,
                     font=('SF Pro Display',9),width=6,anchor='w').pack(side='left')
            e=tk.Entry(rf,textvariable=self.h_vars[i],bg=ENTRY,fg=TEXT,
                       insertbackground=TEXT,relief='solid',bd=1,font=('SF Mono',9),width=7)
            e.pack(side='left');self._h_rows.append(e)

        sec('⚡  E-PARAMS')
        e_lbls=['W_Sp','I_Max','Pul_On','P_Ratio','Voltage','Aux','Speed']
        self._e_frames=[]   # list of (frame, [entry×7]) per cut
        for ci in range(4):
            hdr=tk.Frame(f,bg=SIDEBAR);hdr.pack(fill='x',padx=10,pady=(5,1))
            tk.Label(hdr,text=f'Cut {ci+1}',bg=SIDEBAR,fg=ACCENT,
                     font=('SF Pro Display',8,'bold')).pack(side='left')
            entries=[]
            for lbl,var in zip(e_lbls,self.e_vars[ci]):
                e=row(lbl,var,w=6)
                entries.append(e)
            self._e_frames.append((hdr,entries))
        self._refresh_h()
        self._sidebar_cv = cv   # guardar referencia para scroll global

    def _refresh_h(self,*_):
        try: n=int(self.v_cuts.get())
        except: n=1
        for i,e in enumerate(self._h_rows):
            e.config(state='normal' if i<n else 'disabled')
        for i,(hdr,entries) in enumerate(self._e_frames):
            st='normal' if i<n else 'disabled'
            for e in entries: e.config(state=st)

    def _build_canvas(self,parent):
        # ── Toolbar ─────────────────────────────────────────
        tb_wrap=tk.Frame(parent,bg=PANEL);tb_wrap.pack(fill='x')
        tk.Frame(tb_wrap,bg=BORDER,height=1).pack(fill='x')
        row1=tk.Frame(tb_wrap,bg=PANEL,height=38);row1.pack(fill='x');row1.pack_propagate(False)
        tk.Frame(tb_wrap,bg=BORDER,height=1).pack(fill='x')
        row2=tk.Frame(tb_wrap,bg='#f1f3f4',height=36);row2.pack(fill='x');row2.pack_propagate(False)
        tk.Frame(tb_wrap,bg=BORDER,height=1).pack(fill='x')
        self._tool_btns={}

        def sep(r): tk.Frame(r,bg=BORDER,width=1).pack(side='left',fill='y',pady=5,padx=3)
        def tbtn(txt,cmd,bg=PANEL,fg=TEXT,abg=SEL,key=None,r=row1,bold=False):
            font=('SF Pro Display',9,'bold') if bold else ('SF Pro Display',9)
            b=tk.Button(r,text=txt,command=cmd,bg=bg,fg=fg,relief='flat',
                        font=font,padx=8,pady=5,cursor='hand2',
                        activebackground=abg,activeforeground=fg,bd=0)
            b.pack(side='left',padx=1,pady=3)
            if key: self._tool_btns[key]=(b,bg,fg)
            return b

        # — Fila 1: herramientas de dibujo y edición —
        tbtn('↖ Select',   lambda:self.canvas.set_tool('select'), key='select')
        sep(row1)
        tbtn('/ Línea',    lambda:self.canvas.set_tool('line'),   fg='#1e7e34',abg='#e6f4ea',key='line')
        tbtn('○ Círculo',  lambda:self.canvas.set_tool('circle'), fg='#1e7e34',abg='#e6f4ea',key='circle')
        tbtn('( Arco',     lambda:self.canvas.set_tool('arc'),    fg='#1e7e34',abg='#e6f4ea',key='arc')
        sep(row1)
        tbtn('📐 Medir',   lambda:self.canvas.set_tool('measure'),fg=BLUE, abg=SEL,key='measure')
        sep(row1)
        tbtn('✕ Borrar',   lambda:self.canvas.set_tool('delete'), fg=RED,  abg='#fce8e6',key='delete')
        tbtn('↩ Undo',     lambda:self.canvas.undo(),             fg=ACCENT,abg=SEL)
        sep(row1)
        tbtn('⤷ Path',     lambda:self.canvas.set_tool('path'),   fg='#6200ea',abg='#ede7f6',key='path')
        tbtn('✔ Listo',    self._path_done,                       fg=GREEN, abg='#e6f4ea')
        tbtn('✕ Limpiar',  lambda:self.canvas.clear_path(),       fg=RED,   abg='#fce8e6')
        sep(row1)
        tbtn('⊡ Fit',      lambda:self.canvas._fit_active(),      fg=ACCENT,abg=SEL)
        tbtn('↺ Reset',    self._reset,                           fg=TEXT2, abg='#f1f3f4')

        # — Fila 2: hilo + leads + entrada/salida —
        tk.Label(row2,text='Definir:',bg='#f1f3f4',fg=TEXT2,font=('SF Pro Display',8),padx=6).pack(side='left')
        tbtn('● Hilo',     lambda:self.canvas.set_mode('thread'),  fg=RED,      abg='#fce8e6',key='thread',  r=row2)
        tbtn('▷ Entrada',  lambda:self.canvas.set_mode('entry'),   fg='#b45309',abg='#fef9e0',key='entry',   r=row2)
        sep(row2)
        tbtn('→ Lead-in',  lambda:self.canvas.set_mode('leadin'),  fg=GREEN,    abg='#e6f4ea',key='leadin',  r=row2)
        tbtn('← Lead-out', lambda:self.canvas.set_mode('leadout'), fg='#6200ea',abg='#ede7f6',key='leadout', r=row2)
        sep(row2)
        tk.Label(row2,text='Rotar°',bg='#f1f3f4',fg=TEXT2,font=('SF Pro Display',8),padx=4).pack(side='left')
        tk.Entry(row2,textvariable=self.v_rotate,bg=ENTRY,fg=TEXT,insertbackground=TEXT,
                 relief='solid',bd=1,font=('SF Mono',9),width=5,
                 highlightthickness=1,highlightbackground=BORDER,highlightcolor=ACCENT
                 ).pack(side='left',pady=5)
        tbtn('↻ Aplicar',self._rotate,fg='#6200ea',abg='#ede7f6',r=row2)

        self.canvas=DXFCanvas(parent,on_changed=self._gen,status_cb=self._st)
        self.canvas.on_tool=self._highlight_tool
        self.canvas._open_cb=self._open
        self.canvas.pack(fill='both',expand=True)
        self.bind_all('<Control-z>',lambda e:self.canvas.undo())
        self.bind_all('<Control-Z>',lambda e:self.canvas.undo())

        def _global_scroll(e):
            # Solo scroll el sidebar si el cursor está dentro de él
            wx = e.widget.winfo_rootx() - self.winfo_rootx()
            if wx < 275:   # sidebar tiene 270px de ancho
                delta = e.delta
                units = int(-1*delta/120) if abs(delta)>=120 else (-1 if delta>0 else 1)
                self._sidebar_cv.yview_scroll(units,'units')
        self.bind_all('<MouseWheel>', _global_scroll, add='+')

        # Leyenda de colores
        leg=tk.Frame(parent,bg=PANEL);leg.pack(fill='x',padx=8,pady=3)
        tk.Frame(parent,bg=BORDER,height=1).pack(fill='x')
        for col,txt in [(RED,'Hilo'),(YELLOW,'Entrada'),('#c45000','Salida'),
                        (GREEN,'Lead-in'),(BLUE,'Activo'),('#f9ab00','Kerf'),
                        ('#bdc1c6','Ref')]:
            tk.Frame(leg,bg=col,width=9,height=9).pack(side='left',padx=(4,1))
            tk.Label(leg,text=txt,bg=PANEL,fg=TEXT2,font=('SF Pro Display',8)).pack(side='left',padx=(0,6))
        tk.Label(leg,text='Scroll=zoom  ·  Arrastrar=pan  ·  Ctrl+Z=deshacer',
                 bg=PANEL,fg=TEXT2,font=('SF Pro Display',8)).pack(side='right',padx=4)

    def _highlight_tool(self,active_key):
        for key,(btn,bg,fg) in self._tool_btns.items():
            if key==active_key:
                btn.config(bg=ACCENT,fg='white',relief='flat',font=('SF Pro Display',9,'bold'))
            else:
                btn.config(bg=bg,fg=fg,relief='flat',font=('SF Pro Display',9))

    def _build_code(self,parent):
        hdr=tk.Frame(parent,bg=PANEL);hdr.pack(fill='x',padx=8,pady=(8,2))
        tk.Label(hdr,text='Código ISO',bg=PANEL,fg=TEXT,
                 font=('SF Pro Display',10,'bold')).pack(side='left')
        self.code_box=scrolledtext.ScrolledText(parent,bg='#f8f9fa',fg='#202124',
            insertbackground=TEXT,font=('SF Mono',10),relief='flat',wrap='none',
            state='disabled',bd=0,padx=8,pady=6)
        self.code_box.pack(fill='both',expand=True,padx=6,pady=(0,6))
        for tag,col in [('cmt',TEXT2),('g','#1967d2'),('m','#c45000'),('ep','#6200ea'),('comp',GREEN)]:
            self.code_box.tag_config(tag,foreground=col)

    def _open(self):
        path=filedialog.askopenfilename(title='Seleccionar DXF',
            filetypes=[('DXF','*.dxf *.DXF'),('Todos','*.*')])
        if path: self.v_dxf.set(path);self._load(path)

    def _load(self,path):
        try:
            layer=self.v_layer.get().strip() or None
            segs,sc,units=read_dxf(path,layer)
            if not segs: self._st('Sin entidades en el DXF.',True);return
            contours=find_contours(segs)
            self._units=units
            self.lbl_units.config(
                text=f'Unidades: {units}  •  {len(contours)} contorno(s)  •  {len(segs)} segs')
            self.canvas.load(segs,contours)
            self._st(f'Cargado: {os.path.basename(path)}  ({units}, {len(contours)} contornos)')
            self._gen()
        except Exception as e:
            self._st(f'Error: {e}',True);import traceback;traceback.print_exc()

    def _params(self):
        def f(v,d=0.):
            try: return float(v.get())
            except: return d
        def i(v,d=0):
            try: return int(v.get())
            except: return d
        cuts=i(self.v_cuts,1)
        offsets=[i(self.h_vars[j],H_DEF[j]) for j in range(cuts)]
        eparams=[{k:i(v) for k,v in zip(self.e_keys,self.e_vars[j])}
                 for j in range(cuts)]
        tw=self.canvas.thread_world
        lw=self.canvas.leadin_world;low=self.canvas.leadout_world
        same=self.v_same_lead.get()
        if same and lw: low=lw
        cutin=self.v_cutin.get()
        return {
            'mode':self.v_mode.get(),'cutin':cutin,'comp':self.v_comp.get(),'cuts':cuts,
            'thread_x':tw[0] if tw else None,'thread_y':tw[1] if tw else None,
            'exit_seg':self.canvas.exit_seg,   # índice de segmento de salida
            'leadin_x' :lw[0]  if lw  else None,
            'leadin_y' :lw[1]  if lw  else None,
            'leadout_x':low[0] if low else None,
            'leadout_y':low[1] if low else None,
            'same_lead':same,'force_exit':self.v_force_exit.get(),
            'leadin_angle' :f(self.v_leadin_angle,  None) if self.v_leadin_angle.get().strip()  else None,
            'leadout_angle':f(self.v_leadout_angle, None) if self.v_leadout_angle.get().strip() else None,
            'leadin_length':f(self.v_leadin,3.),'overcut':f(self.v_overcut,0.),
            'cut_speed':f(self.v_cutspeed,2.),
            'material':self.v_mat.get() or 'SKD11','thickness':f(self.v_thick,10.),
            'wire':f(self.v_wire,.18),'flush':self.v_flush.get() or 'DIC206',
            'offsets':offsets,'eparams':eparams}

    def _gen(self):
        chain=self.canvas.active_chain()
        if not chain: return
        try:
            p=self._params();code,info=generate_iso(chain,p)
            self._code=code;self._show_code(code);self.canvas.update_info(info)
            nc=len(self.canvas.contours);ac=self.canvas.active_idx
            tstr=self._fmt_min(info.get('est_min',0))
            gouges=info.get('gouges',[])
            if gouges:
                self._st(f"⚠  {len(gouges)} radio(s) ≤ offset — RIESGO DE GOUGE/ALARMA: "
                         f"{gouges[0][2]}"+('  (+más)' if len(gouges)>1 else ''),True)
            else:
                self._st(f"✓  Contorno {ac+1}/{nc}  |  {info['direction']}  |  {info['comp']}  |  "
                         f"{p['cuts']} pasada(s)  |  ⏱ {tstr}  |  Entry({info['sx']:.1f},{info['sy']:.1f})mm")
        except Exception as e:
            self._st(f'Error: {e}',True);import traceback;traceback.print_exc()

    @staticmethod
    def _fmt_min(m):
        if m<=0: return '—'
        h=int(m//60);mm=int(round(m%60))
        return f'{h}h {mm:02d}m' if h else f'{mm}m'

    def _toggle_kerf(self):
        self.canvas.show_kerf=self.v_kerf.get()
        self.canvas._draw()

    def _gen_all(self):
        """Genera UN programa con todos los contornos de la placa."""
        if not self.canvas.contours:
            self._st('⚠  Carga un DXF primero',True); return
        try:
            p=self._params()
            code=generate_iso_multi(self.canvas.contours,p)
            self._code=code;self._show_code(code)
            self._st(f'✓  Programa múltiple: {len(self.canvas.contours)} contornos '
                     f'(interiores primero) — 💾 Guardar .ISO para exportar')
        except Exception as e:
            self._st(f'Error: {e}',True);import traceback;traceback.print_exc()

    # ── Presets de material ──────────────────────────
    def _preset_refresh(self):
        self._preset_cb['values']=sorted(load_presets().keys())

    def _preset_save(self):
        t=self.v_thick.get().strip() or '?'
        name=f"{self.v_mat.get().strip() or 'MAT'} {t}mm ø{self.v_wire.get().strip()}"
        d=load_presets()
        d[name]={'mode':self.v_mode.get(),'cuts':int(self.v_cuts.get() or 1),
                 'material':self.v_mat.get(),'thickness':self.v_thick.get(),
                 'wire':self.v_wire.get(),'flush':self.v_flush.get(),
                 'leadin':self.v_leadin.get(),'overcut':self.v_overcut.get(),
                 'cutspeed':self.v_cutspeed.get(),
                 'H':[v.get() for v in self.h_vars],
                 'E':[[v.get() for v in fila] for fila in self.e_vars]}
        save_presets(d)
        self._preset_refresh();self.v_preset.set(name)
        self._st(f'💾  Preset guardado: {name}')

    def _preset_load(self,*_):
        d=load_presets();name=self.v_preset.get()
        if name not in d: return
        pr=d[name]
        self.v_mode.set(pr.get('mode','Core'));self.v_cuts.set(pr.get('cuts',1))
        self.v_mat.set(pr.get('material',''));self.v_thick.set(pr.get('thickness','10'))
        self.v_wire.set(pr.get('wire','0.18'));self.v_flush.set(pr.get('flush','DIC206'))
        self.v_leadin.set(pr.get('leadin','3.0'));self.v_overcut.set(pr.get('overcut','0.0'))
        self.v_cutspeed.set(pr.get('cutspeed','2.0'))
        for v,val in zip(self.h_vars,pr.get('H',[])): v.set(val)
        for fila,vals in zip(self.e_vars,pr.get('E',[])):
            for v,val in zip(fila,vals): v.set(val)
        self._refresh_h();self._gen()
        self._st(f'✓  Preset cargado: {name}')

    def _preset_delete(self):
        d=load_presets();name=self.v_preset.get()
        if name not in d: return
        del d[name];save_presets(d)
        self._preset_refresh();self.v_preset.set('')
        self._st(f'🗑  Preset borrado: {name}')

    def _apply_leadin_angle(self):
        chain=self.canvas.active_chain()
        if not chain: self._st('⚠  Carga un DXF primero',True); return
        try:
            angle=float(self.v_leadin_angle.get())
            dist =float(self.v_leadin.get())
        except:
            self._st('⚠  Ángulo y distancia deben ser números',True); return
        sx,sy=chain[0]['start']
        a=math.radians(angle)
        self.canvas.leadin_world=(sx - dist*math.cos(a), sy - dist*math.sin(a))
        self._gen()
        self._st(f'✓  Lead-in: {dist}mm a {angle}° → ({self.canvas.leadin_world[0]:.2f}, {self.canvas.leadin_world[1]:.2f}) mm')

    def _apply_leadout_angle(self):
        chain=self.canvas.active_chain()
        if not chain: self._st('⚠  Carga un DXF primero',True); return
        try:
            angle=float(self.v_leadout_angle.get())
            dist =float(self.v_leadin.get())
        except:
            self._st('⚠  Ángulo debe ser número',True); return
        ex,ey=chain[-1]['end']
        a=math.radians(angle)
        self.canvas.leadout_world=(ex + dist*math.cos(a), ey + dist*math.sin(a))
        self._gen()
        self._st(f'✓  Lead-out: {dist}mm a {angle}° → ({self.canvas.leadout_world[0]:.2f}, {self.canvas.leadout_world[1]:.2f}) mm')

    def _path_done(self):
        """Termina el modo Path, vuelve a Select y genera el G-code."""
        n=len(self.canvas.custom_path)
        if n==0:
            self._st('⚠️  No hay segmentos en el path — usa 🛤 Path para seleccionarlos',True)
            return
        self.canvas.set_tool('select')
        self._gen()
        self._st(f'✓  Path de {n} segmento(s) listo — código generado  |  🧹 Limpiar para volver a modo automático')

    def _reset(self):
        self.canvas.thread_world=None;self.canvas.exit_world=None
        self.canvas.leadin_world=None;self.canvas.leadout_world=None
        self.canvas.entry_seg=0;self.canvas.exit_seg=None
        self.canvas._draw_pts=[];self.canvas.custom_path=[]
        self.canvas.set_tool('select')
        self.canvas._fit_active();self._gen()

    def _rotate(self):
        try: angle=float(self.v_rotate.get())
        except: self._st('⚠  Ingresa un ángulo válido (ej: 90, -45)',True); return
        if not self.canvas.all_segs:
            self._st('⚠  Carga un DXF primero',True); return
        self.canvas._snapshot()
        self.canvas.all_segs=rotate_segs(self.canvas.all_segs,angle)
        self.canvas.thread_world=None;self.canvas.exit_world=None
        self.canvas.leadin_world=None;self.canvas.leadout_world=None
        self.canvas._rebuild()
        self.canvas._fit_active()
        self._st(f'✓  Rotado {angle}°  (Ctrl+Z para deshacer)')

    def _save(self):
        if not self._code: self._gen()
        if not self._code: return
        base=os.path.splitext(self.v_dxf.get())[0] if self.v_dxf.get() else 'salida'
        path=filedialog.asksaveasfilename(title='Guardar ISO',defaultextension='.ISO',
            initialfile=os.path.basename(base)+'.ISO',
            filetypes=[('ISO','*.ISO *.iso *.nc'),('Todos','*.*')])
        if path:
            with open(path,'w',newline='\r\n',encoding='ascii',errors='replace') as fh:
                fh.write(self._code)
            self._st(f'✓  Guardado: {os.path.basename(path)}')

    def _show_code(self,code):
        self.code_box.config(state='normal');self.code_box.delete('1.0','end')
        self.code_box.insert('end',code)
        for i,line in enumerate(code.splitlines(),1):
            ln=line.strip();tag=None
            if ln.startswith('(') or ln.startswith(';'): tag='cmt'
            elif ln.startswith(('G0','G9','G4','G5')): tag='g'
            elif ln.startswith(('M0','M9','M2','M1')): tag='m'
            elif ln.startswith(('E','H','N')): tag='ep'
            elif ln in ('G41','G42','G40','G50'): tag='comp'
            if tag: self.code_box.tag_add(tag,f'{i}.0',f'{i}.end')
        self.code_box.config(state='disabled')

    def _st(self,msg,err=False):
        self.lbl_st.config(text=msg,fg=ACCENT if err else GREEN)

    # ─── SIMULACIÓN ───────────────────────────────────────────────────────────
    def _simulate(self):
        chain=self.canvas.active_chain()
        if not chain:
            self._st('⚠  Carga un DXF primero',True); return
        if not self._code: self._gen()
        try:
            p=self._params(); _,info=generate_iso(chain,p)
        except Exception as e:
            self._st(f'Error: {e}',True); import traceback; traceback.print_exc(); return

        # ── Construir lista de (x,y) en orden real del recorrido ──
        def lp(x0,y0,x1,y1):
            d=pdist((x0,y0),(x1,y1)); n=max(3,int(d/0.3))
            return [(x0+(x1-x0)*t/n, y0+(y1-y0)*t/n) for t in range(n+1)]
        def ap(cx,cy,r,sa,ea,ccw):
            sa_r=math.radians(sa); ea_r=math.radians(ea)
            if ccw:
                if ea_r<=sa_r+1e-9: ea_r+=2*math.pi
            else:
                if ea_r>=sa_r-1e-9: ea_r-=2*math.pi
            arc_len=abs(ea_r-sa_r)*r; n=max(6,int(arc_len/0.3))
            return [(cx+r*math.cos(sa_r+(ea_r-sa_r)*t/n),
                     cy+r*math.sin(sa_r+(ea_r-sa_r)*t/n)) for t in range(n+1)]

        tx,ty = info['tx'],info['ty']
        lx,ly = info['lx'],info['ly']
        sx,sy = info['sx'],info['sy']
        ex_lx,ex_ly = info['ex_lx'],info['ex_ly']
        last_end = chain[-1]['end']

        pts=[]
        pts += lp(tx,ty,lx,ly)         # hilo → lead-in approach
        pts += lp(lx,ly,sx,sy)         # lead-in → entrada contorno
        for seg in chain:
            if seg['type']=='LINE':
                x0,y0=seg['start']; x1,y1=seg['end']
                pts+=lp(x0,y0,x1,y1)
            elif seg['type']=='ARC':
                pts+=ap(seg['cx'],seg['cy'],seg['r'],seg['sa'],seg['ea'],seg['ccw'])
        pts += lp(last_end[0],last_end[1],ex_lx,ex_ly)  # fin contorno → lead-out

        # ── Controles inline en la barra de estado ──
        stop_flag=[False]
        spd=tk.IntVar(value=8)

        # Ocultar label de estado y poner controles inline
        self.lbl_st.pack_forget()
        sim_bar=tk.Frame(self.lbl_st.master,bg=PANEL)
        sim_bar.pack(side='left',fill='y',pady=4,padx=6)
        tk.Label(sim_bar,text='▶ Simulando  Vel:',bg=PANEL,fg=RED,
                 font=('SF Pro Display',9,'bold')).pack(side='left',padx=(0,4))
        tk.Scale(sim_bar,from_=1,to=20,orient='horizontal',variable=spd,
                 bg=PANEL,fg=TEXT,troughcolor='#e8eaed',highlightthickness=0,
                 length=160,showvalue=True,bd=0).pack(side='left')
        def stop():
            stop_flag[0]=True
            sim_bar.destroy()
            self.lbl_st.pack(side='left')
        tk.Button(sim_bar,text='⏹ Detener',command=stop,bg=RED,fg='white',
                  relief='flat',font=('SF Pro Display',9,'bold'),cursor='hand2',
                  padx=8,pady=2).pack(side='left',padx=6)

        # ── Animación en canvas ──
        trail=[]     # líneas del trail (permanecen)
        dot_id=[None]
        prev_c=[None]

        def step(i=0):
            if stop_flag[0]:
                _cleanup(); return
            if i>=len(pts):
                self._st('✓  Simulación completa'); return
            # Process multiple points per frame so speed slider feels responsive
            batch=max(1, spd.get() * 2)
            end=min(i+batch, len(pts))
            for j in range(i, end):
                x,y=pts[j]
                cx,cy=self.canvas.w2c(x,y)
                if prev_c[0]:
                    trail.append(self.canvas.create_line(*prev_c[0],cx,cy,
                                                          fill='#d93025',width=2))
                prev_c[0]=(cx,cy)
            # Draw dot at final position of this batch
            if dot_id[0]:
                try: self.canvas.delete(dot_id[0])
                except: pass
            dot_id[0]=self.canvas.create_oval(cx-6,cy-6,cx+6,cy+6,
                                               fill='#d93025',outline='white',width=2)
            self.canvas.after(16, lambda: step(end))

        def _cleanup():
            for item in trail:
                try: self.canvas.delete(item)
                except: pass
            if dot_id[0]:
                try: self.canvas.delete(dot_id[0])
                except: pass
            try: sim_bar.destroy()
            except: pass
            self.lbl_st.pack(side='left')

        step()

if __name__=='__main__':
    app=App()
    if len(sys.argv)>1 and os.path.exists(sys.argv[1]):
        app.v_dxf.set(sys.argv[1])
        app.after(400,lambda:app._load(sys.argv[1]))
    app.mainloop()
