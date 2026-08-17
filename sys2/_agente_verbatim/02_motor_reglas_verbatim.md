# MOTOR + REGLAS DEFINITIVAS (agente dueño del análisis, 2026-08-16)

## SISTEMA DEFINITIVO (+71.396$) = HÍBRIDO. §41 OBSOLETO (motor viejo, 2.19 ops/día, +12% inflado).
8 cosas:
- ENTRADAS (6): ST-3, ORB, pm_rev, gap_fade, v1, ayer_rev
- REGLAS (5): rebote, descarte ST-1, ratio call/put, skew RETRASA, día bueno
- GESTIÓN (2, SIGUEN ACTIVAS): rodar (delta<0.35), piramidar (delta+0.03)
- INSTRUMENTO: vertical 4 puntos, tope 320$
Config +71.396$: RUMB=0.3, ANCHO=4.0, RETSK=0.04 (skew sobre RETRASA, modo invertir),
                 tope=320, pir=True, aplanado 15:59 (base) / 15:53 (operable, +61.999$).
ratio/skew/día bueno SON del sistema final (aportan +3.030 / +3.874 / +6.433$, cada uno p<0.05).
Nota: se ELIMINÓ "escalar por piramidación" (ahora 800$ = 2 contratos desde inicio por UNIDADES),
      pero la regla intra-operación piramidar SIGUE VIVA.

## ⚠️ CRÍTICO (replicar idéntico o los números no cuadran):
Al RODAR sobre un vertical, lo reconstruye como SINGLE: el pos nuevo NO lleva clave 'vert'
=> pos.get('vert') is None => se valora como una sola pata. Igual con PIRAMIDAR: el contrato
extra ('extra') es un SINGLE, no otro vertical. (El agente no sabe si fue intencional.)

## ===== BUCLE PRINCIPAL verbatim (gestión: gira/rodar/piramidar) =====
# (dentro del loop por minuto h; Sx = spot; Sen = dict hora->'C'/'P' union de entradas)
gira = h in Sen and Sen[h]!=pos['rt']
dl=None
T=max(1e-6,(960-mm(h))/(60*24*252))
s_=iv(pos['mid'],Sx,pos['k'],T,pos['rt']=='C')
if s_:
    d_,_,_=greeks(Sx,pos['k'],T,s_,pos['rt']=='C'); dl=abs(d_)
if pir and not pos['extra'] and not gira and h<"15:20" and mm(h)-mm(pos['h0'])>=10 \
   and dl is not None and pos['d0'] is not None and dl-pos['d0']>0.03:
    cd=[(k,v) for (r_,k),v in PM[h].items() if r_==pos['rt']]
    e=elegir(cd,Sx,h,pos['rt'],modo_strike,tope)
    if e: pos['extra']=dict(k=e[0],ask=e[1][0]*1.01,mid=e[1][0])
rodar=(not gira and pos['rod']<3 and h<"15:30" and dl is not None and dl<0.35 and not pos['extra'])
if pos['extra']:
    _i2=max(0.0,(Sx-pos['extra']['k']) if pos['rt']=='C' else (pos['extra']['k']-Sx))
    q2=PM[h].get((pos['rt'],pos['extra']['k']))
    pos['extra']['mid']=max(q2[0],_i2) if q2 else max(pos['extra']['mid'],_i2)
if gira or h>="15:59":
    g=(pos['mid']-pos['ask'])*100-1.72
    if pos['extra']: g+=(pos['extra']['mid']-pos['extra']['ask'])*100-1.72
    tot+=g; hechas+=1; pos=None
elif rodar:
    tot+=(pos['mid']-pos['ask'])*100-1.72
    rt=pos['rt']; r2=pos['rod']+1; h0=pos['h0']; pos=None
    cd=[(k,v) for (r_,k),v in PM[h].items() if r_==rt]
    e=elegir(cd,Sx,h,rt,modo_strike,tope)
    if e:
        T=max(1e-6,(960-mm(h))/(60*24*252)); s_=iv(e[1][0],Sx,e[0],T,rt=='C'); d0=None
        if s_:
            dd,_,_=greeks(Sx,e[0],T,s_,rt=='C'); d0=abs(dd)
        pos={'k':e[0],'rt':rt,'ask':e[1][0]*1.01,'mid':e[1][0],'rod':r2,
             'extra':None,'h0':h0,'d0':d0}   # <-- SIN 'vert' => single

## ===== APERTURA DE POSICIÓN verbatim (ratio + selección de contrato) =====
if pos is None and h in Sen and hechas<4 and h<"15:40":
    rt=Sen[h]
    if RUMB:
        rr=ratio_otm(PM[h],Sx)
        if rr is not None:
            if rt=='C' and rr<RUMB: continue
            if rt=='P' and rr>1.0/RUMB: continue
    cd=[(k,v) for (r_,k),v in PM[h].items() if r_==rt]
    if ANCHO:
        cd2=[(k,suelo(k,v,Sx,rt)) for k,v in cd]
        ev=elegir_vert(cd2,Sx,h,rt,tope,ANCHO)
        if ev:
            kl,pl,ksh,psh=ev
            T=max(1e-6,(960-mm(h))/(60*24*252)); s_=iv(pl,Sx,kl,T,rt=='C'); d0=None
            if s_:
                dd,_,_=greeks(Sx,kl,T,s_,rt=='C'); d0=abs(dd)
            pos={'k':kl,'ks':ksh,'rt':rt,'ask':(pl-psh)*1.01,'mid':pl-psh,
                 'rod':0,'extra':None,'h0':h,'d0':d0,'vert':True}
            continue
    e=elegir(cd,Sx,h,rt,modo_strike,tope)
    if e:
        T=max(1e-6,(960-mm(h))/(60*24*252)); s_=iv(e[1][0],Sx,e[0],T,rt=='C'); d0=None
        if s_:
            dd,_,_=greeks(Sx,e[0],T,s_,rt=='C'); d0=abs(dd)
        pos={'k':e[0],'rt':rt,'ask':e[1][0]*1.01,'mid':e[1][0],'rod':0,
             'extra':None,'h0':h,'d0':d0}

## ===== AUXILIARES verbatim =====
def suelo(k,v,S,rt):
    intr=max(0.0,(S-k) if rt=='C' else (k-S))
    return (max(v[0],intr),)+tuple(v[1:])

def ratio_otm(m, S):
    voc=sum(v[1] for (r,k),v in m.items() if r=='C' and k>S)
    vop=sum(v[1] for (r,k),v in m.items() if r=='P' and k<S)
    if voc+vop<30: return None
    return voc/max(1.0,vop)

def elegir_vert(cands, S, h, rt, tope, ancho):
    cs=sorted(cands, key=lambda x: -((S-x[0]) if rt=='C' else (x[0]-S)))
    for kl,vl in cs:
        mny=(S-kl) if rt=='C' else (kl-S)
        if mny<0.5: continue
        ks_obj = kl+ancho if rt=='C' else kl-ancho
        cand_s=[(k,v) for k,v in cands if abs(k-ks_obj)<0.01]
        if not cand_s: continue
        ksh,vsh=cand_s[0]
        deb=(vl[0]-vsh[0])*100
        if 20<=deb<=tope:
            return (kl,vl[0],ksh,vsh[0])
    return None

# elegir (modo presupuesto/single): filtra v[0]*100<=tope y devuelve max(c, key=lambda x: x[1][0])
#   = el más caro que quepa = ITM más profundo.

## PENDIENTE de pedir verbatim (agente 75% weekly limit, dosificar):
# - descarte ST-1 (params del Supertrend de 1 min + ventana 5 min) [REGLA]
# - skew sobre RETRASA (cómo RETSK=0.04 modifica el grupo RETRASA -> invertir) [REGLA]
# - día bueno (efic60<0.187 & mov_DIA>1.23 & mov_TLT<1.225 -> doblar unidades) [REGLA]
# - construcción de Sen = unión de las 6 entradas + descartar_cerca_orb (orden ORB,pm_rev,v1,gap_fade,ayer_rev)
# - funciones iv() y greeks() del motor (probable = mi greeks.py; confirmar firma iv(precio,S,K,T,esC))
# - modo_strike (param de elegir) y su valor en la config +71.396$

## ===== LAS 4 PIEZAS FINALES verbatim (agente, 2026-08-16) =====

## (1) DESCARTE ST-1
def st_full(bars, tf, per=7, mult=3.0):
    b={}
    for h,hi,lo,cl in bars:
        s=(mm(h)//tf)*tf
        a=b.setdefault(s,{"hi":hi,"lo":lo,"cl":cl,"o":None})
        if a["o"] is None: a["o"]=cl
        a["hi"]=max(a["hi"],hi); a["lo"]=min(a["lo"],lo); a["cl"]=cl
    ks=sorted(b)
    if len(ks)<per+2: return {},[]
    HI=[b[s]["hi"] for s in ks];LO=[b[s]["lo"] for s in ks];CL=[b[s]["cl"] for s in ks]
    tr=[];atr=[]
    for i in range(len(CL)):
        t=HI[i]-LO[i] if i==0 else max(HI[i]-LO[i],abs(HI[i]-CL[i-1]),abs(LO[i]-CL[i-1]))
        tr.append(t); atr.append(sum(tr)/len(tr) if i<per else atr[-1]+(t-atr[-1])/per)
    d=-1;fu=fl=None;out={}
    for i in range(len(ks)):
        m=(HI[i]+LO[i])/2; ub=m+mult*atr[i]; lb=m-mult*atr[i]
        if i==0: fu,fl=ub,lb
        else:
            fu=ub if (ub<fu or CL[i-1]>fu) else fu
            fl=lb if (lb>fl or CL[i-1]<fl) else fl
        if d==1 and CL[i]<fl: d=-1
        elif d==-1 and CL[i]>fu: d=1
        out[ks[i]]=dict(d=d,linea=fl if d==1 else fu,cl=CL[i],o=b[ks[i]]["o"],hi=HI[i],lo=LO[i],atr=atr[i])
    return out, ks

def giros(S1,k1,h,N=5):
    m0=mm(h)
    sub=[S1[x]['d'] for x in k1 if m0<=x<m0+N and x in S1]
    if len(sub)<2: return 0
    return sum(1 for z in range(1,len(sub)) if sub[z]!=sub[z-1])
# S1,k1=st_full(bars,1)  per=7 mult=3.0. Ventana N=5 semiabierta [m0,m0+5). En loop: if giros(...)>=1: continue

## (2) SKEW sobre RETRASA (RETMOD='invierte', RETSK=0.04)
def skew_l2(m,S,h,lado):
    T=max(1e-6,(960-mm(h))/(60*24*252))
    ivp=[]; ivc=[]
    for (r,k),v in m.items():
        d=(k-S) if r=='C' else (S-k)
        if not (0.8<d<3.5): continue
        s_=iv(max(v[0],0.01),S,k,T,r=='C')
        if s_ and 0.03<s_<3: (ivc if r=='C' else ivp).append(s_)
    if len(ivp)<2 or len(ivc)<2: return None
    import statistics as _st
    return (_st.median(ivp)-_st.median(ivc))*lado
# en el loop de flips (ANTES de p+=reb2):
#   if RETMOD:
#       _r=reb2(L,ks,ik,h,d)
#       _esret = bool(_r) and _r[0][0]!=h and _r[0][1]==d
#       if _esret:
#           _lado=1 if d=='C' else -1
#           _S=cl_.get(h); _m=PREM.get(fk,{}).get(h)
#           _sk=skew_l2(_m,_S,h,_lado) if (_m and _S is not None) else None
#           _mal=(_sk is not None and _sk>RETSK)
#           if _mal:
#               _hh=_r[0][0]
#               if RETMOD=='quita' or _hh>="15:40": continue
#               if RETMOD=='invierte':
#                   p.append((_hh,'P' if d=='C' else 'C')); continue
# (G2V=False, DIAG=False -> vias extra inactivas)

## (3) DÍA BUENO (E60B=0.187, MDB=1.23, MTB=1.225)
# BUENO_HOY=False
# if DIABUENO:
#     _hs=sorted(cl_)
#     if len(_hs)>60:
#         _sg=[cl_[x] for x in _hs[:60]]
#         _rc=sum(abs(_sg[i]-_sg[i-1]) for i in range(1,len(_sg)))
#         _e60=abs(_sg[-1]-_sg[0])/_rc if _rc else 9
#         def _mvetf(_n):
#             _b=ETFB.get(_n,{}).get(fk)
#             if not _b: return None
#             _h9=[x for x in _b if "09:30"<=x[0]<="10:00"]
#             if len(_h9)<20: return None
#             return (_h9[-1][3]-_h9[0][3])/max(0.01,_h9[0][3])*1000
#         _md=_mvetf("DIA"); _mt=_mvetf("TLT")
#         if _e60<E60B and _md is not None and _md>MDB and _mt is not None and _mt<MTB:
#             BUENO_HOY=True
# En apertura pos: 'nq':(2 if BUENO_HOY else 1). P&L: g=((mid-ask)*100-1.72)*pos.get('nq',1)
# ETFB[n][fk] = lista de (hora,hi,lo,cl); indice [3]=cierre. _hs[:60]=primeros 60 min RTH.

## (4) CONSTRUCCIÓN DE Sen (unión de las 6 entradas)
# orb_en: IDENTICO al mio (rango_min=0.40). 
# S=[]
# for a in ("09:40","11:00"):
#     s=orb_en(bars,a)
#     if s: S+=s
# for ex in extra:                       # extra=('pm_rev','v1','gap_fade','ayer_rev')  ORDEN IMPORTA
#     sg=señales_apertura(bars,ph,pl,pc,ex)
#     if sg and all(abs(mm(sg[0][0])-mm(x[0]))>5 for x in S): S+=sg    # >5 no >=5, contra TODO S
# p=[]
# for h,d in sp:                          # sp = sen_p(bars,7,3.0)[0]
#     if h<"09:45": continue
#     if giros(S1,k1,h,5)>=1: continue    # ST-1 ANTES del rebote
#     if RETMOD: ...bloque skew...        # (arriba; con continue cuando invierte)
#     p+=reb2(L,ks,ik,h,d)
# sen=sorted(set(S+p)); Sen=dict(sen)     # dict colapsa colisiones mismo minuto: P>C (alfabetico)
#
# 5 GOTCHAS: (a) extra en orden pm_rev,v1,gap_fade,ayer_rev; (b) descarte >5 no >=5, contra ORB+aperturas ya aceptadas;
# (c) ST-1 antes del rebote (flip descartado por ST-1 no entra a reb2); (d) Sen=dict colapsa mismo-minuto P sobre C;
# (e) ORB reversion por construccion (C>hi->'P').

## ===== MOTOR SIS70 — setup + valoración + cierre verbatim (agente, 2026-08-16) =====
# PM[h][(right,strike)] = (close, vol)  -- v[0]=CLOSE del agregado 1-min massive (NO mid/bid), v[1]=vol. 2 campos.
# prev = (max_ayer, min_ayer, cierre_ayer). Sx = cl_[h] (spot=close SPY del minuto).

def SIS70(extra=('pm_rev','v1','gap_fade','ayer_rev'), modo_strike='presupuesto', tope=320.0, pir=True):
    D={}; prev=None
    for fk,bars,rth in sesiones():
        if DESDE and fk<DESDE: continue
        if HASTA and fk>=HASTA: continue
        cl_={h:x for h,x,_,_,_ in rth}
        if len(cl_)<100 or fk not in PREM:
            if cl_:
                hsd=sorted(cl_); prev=(max(cl_.values()),min(cl_.values()),cl_[hsd[-1]])
            continue
        PM=PREM[fk]
        ph,pl,pc = prev if prev else (None,None,None)
        # ... construccion de sp,L,ks,ik,S1,k1,S,p,sen (ya lo tengo; S2,k2 solo si G2V, inactivo)
        Sen=dict(sen); tot=0.0; pos=None; hechas=0
        for h in sorted(PM):              # ITERA MINUTOS CON PREMIUM (no cl_)
            if h<'09:30' or h>'16:00': continue
            Sx=cl_.get(h)
            if Sx is None: continue
            # --- (b) VALORACION antes de gira/rodar/piramidar ---
            if pos:
                _intr=max(0.0,(Sx-pos['k']) if pos['rt']=='C' else (pos['k']-Sx))
                q=PM[h].get((pos['rt'],pos['k']))
                _long=max(q[0],_intr) if q else max(pos.get('_l',_intr),_intr)
                pos['_l']=_long
                if pos.get('vert'):
                    _is=max(0.0,(Sx-pos['ks']) if pos['rt']=='C' else (pos['ks']-Sx))
                    q2=PM[h].get((pos['rt'],pos['ks']))
                    _sh=max(q2[0],_is) if q2 else max(pos.get('_s',_is),_is)
                    pos['_s']=_sh
                    pos['mid']=_long-_sh
                else:
                    pos['mid']=_long
            # --- aqui va el bloque gira/rodar/piramidar (ya lo tengo) ---
            # --- luego apertura (ya la tengo) ---
        D[fk]=tot
        hsd=sorted(cl_); prev=(max(cl_.values()),min(cl_.values()),cl_[hsd[-1]])
    return D
# No hay cierre forzado: aplana dentro del bucle con if gira or h>="15:59". PM cubre hasta 16:00.
# elegir presupuesto: if modo=='presupuesto': c=[(k,v) for k,v in cands if v[0]*100<=tope]; if not c: return None; return max(c,key=lambda x:x[1][0])
# AVISOS: (1) valora ANTES de comprobar gira (señal contraria en mismo h: valora, luego cierra a ese precio).
#         (2) for h in sorted(PM) itera minutos con premium; minuto con SPY pero sin contratos se SALTA.

## ===== FIX día bueno (nq) + señales_apertura VERBATIM (agente, 2026-08-16) =====
## (1) CIERRE con día bueno: nq SOLO en principal y rodado, NO en el extra. nq guardado en pos.
if gira or h>="15:59":
    g=((pos['mid']-pos['ask'])*100-1.72)*pos.get('nq',1)
    if pos['extra']: g+=(pos['extra']['mid']-pos['extra']['ask'])*100-1.72   # extra SIN nq
    tot+=g; hechas+=1; pos=None
elif rodar:
    tot+=((pos['mid']-pos['ask'])*100-1.72)*pos.get('nq',1)                   # rodado CON nq
    rt=pos['rt']; r2=pos['rod']+1; h0=pos['h0']; pos=None
    cd=[(k,v) for (r_,k),v in PM[h].items() if r_==rt]
    e=elegir(cd,Sx,h,rt,modo_strike,tope)
    if e:
        T=max(1e-6,(960-mm(h))/(60*24*252)); s_=iv(e[1][0],Sx,e[0],T,rt=='C'); d0=None
        if s_: dd,_,_=greeks(Sx,e[0],T,s_,rt=='C'); d0=abs(dd)
        pos={'k':e[0],'rt':rt,'ask':e[1][0]*1.01,'mid':e[1][0],'rod':r2,'extra':None,'h0':h0,'d0':d0}
        # <-- pos reconstruida SIN 'nq' -> tras el primer rodado vuelve a tamaño 1 aunque sea dia bueno
# => nq se GUARDA en pos al abrir ('nq':nq). En cierre usar pos.get('nq',1). Extra sin nq.

## (2) señales_apertura VERBATIM (aperturas SOLO miran 09:30-10:00; rupturas por CIERRE [2])
def señales_apertura(bars, prev_hi, prev_lo, prev_cl, modo):
    B={h:(hi,lo,cl) for h,hi,lo,cl in bars}
    hs=sorted(B)
    pm=[h for h in hs if h<'09:30']
    if not pm: return []
    pm_hi=max(B[h][0] for h in pm); pm_lo=min(B[h][1] for h in pm)
    rth=[h for h in hs if '09:30'<=h<'10:00']
    if len(rth)<20: return []
    op=B[rth[0]][2]
    if modo=='pm_rev':
        for h in rth:
            if B[h][2]>pm_hi: return [(h,'P')]
            if B[h][2]<pm_lo: return [(h,'C')]
    elif modo=='pm_seg':
        for h in rth:
            if B[h][2]>pm_hi: return [(h,'C')]
            if B[h][2]<pm_lo: return [(h,'P')]
    elif modo=='ayer_rev':
        if prev_hi is None: return []
        for h in rth:
            if B[h][2]>prev_hi: return [(h,'P')]
            if B[h][2]<prev_lo: return [(h,'C')]
    elif modo=='gap_fade':
        if prev_cl is None: return []
        g=op-prev_cl
        if abs(g)<0.4: return []
        return [(rth[3],'P' if g>0 else 'C')]
    elif modo=='v1':
        p5=[h for h in rth if h<'09:35']
        if len(p5)<4: return []
        h5=max(B[h][0] for h in p5); l5=min(B[h][1] for h in p5)
        if h5-l5<0.30: return []
        for h in rth:
            if h<'09:35': continue
            if B[h][2]>h5: return [(h,'P')]
            if B[h][2]<l5: return [(h,'C')]
    return []
# CLAVE: rth = '09:30'<=h<'10:00' (solo primeros 30 min); ruptura por CIERRE (B[h][2]);
# pm_hi/pm_lo = hi/lo del premarket; gap_fade dispara en rth[3] (4a barra) si |gap|>=0.40;
# v1 rango >=0.30 desde 09:35. prev_hi/lo/cl = max_ayer/min_ayer/cierre_ayer.
