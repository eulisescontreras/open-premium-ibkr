# REBOTE (§10.5) — correcciones del agente que tiene reb2() real (2026-08-16)

FUENTE: agente claude.ai (conversación de266178...) que inspeccionó el código REAL reb2()
que produjo las cifras validadas. El PDF §10.5 "implementación exacta" NO es fiel.
Tratar como HIPÓTESIS FUERTE hasta reproducir 675/393/243/100 con cold run (R5/R8).

## Correcciones vs PDF:
1. Universo del rebote: 1.411 flips, 479 días, SOLO señales ST-3 (NO ORB, NO aperturas;
   esas van en lista S separada, nunca pasan por reb2). Filtros:
   - día presente en cadena premium (485 días con datos)
   - "09:45" <= hora <= "15:30"
   - índice bucket j >= 10  y  j+13 < len(ks)
   - ATR > 0
   - segmento hasta el flip siguiente con >= 3 cierres
2. Distribución + falsos (falso = avance < 1.0 ATR antes del siguiente flip):
   grupo     n    (A1/A2 split)   falsosA1   falsosA2
   NORMAL   675   334/341         12.3%      9.1%
   RETRASA  393   194/199         42.8%      42.2%
   INVIERTE 243   127/116         53.5%      62.1%
   DESCARTA 100   48/52           31.2%      40.4%
3. VENTANA = 12 buckets (36 min), NO 8. Firma:
   reb2(L, ks, ik, h, d, espera=12, cerca=1.0, sep=1.5, pegado=2)
   ATR = mean sobre range(max(0,i-10), i+1) = [i-10,i] inclusive (hasta 11 buckets). OK.
4. linea = fl if d==1 else fu  (mismo valor que st_dir, mismo bucle).
5. o NO es el open del bucket -> es el CLOSE del primer minuto del bucket:
   a = b.setdefault(s, {"hi":hi,"lo":lo,"cl":cl,"o":None}); if a["o"] is None: a["o"]=cl
6. Clasificación:
   if not r_: gr='DESCARTA'
   elif r_[0][0]==h and r_[0][1]==d: gr='NORMAL'
   elif r_[0][1]!=d: gr='INVIERTE'
   else: gr='RETRASA'
   - Matiz A: toque solo si contra>=1 (buckets con (cl-o)*lado < 0).
   - Matiz B: DESCARTA agrupa: (a) tocó y no resolvió en 12 buckets; (b) resolvió pero hh>=15:40 -> [].
7. sen_p termina con shift_sen(out,3). YO SÍ lo tengo (exp_timing_realista.py). OK.

## PENDIENTE: pedí el CÓDIGO FUENTE COMPLETO VERBATIM de reb2 + construcción de L + loop llamador.
Transcribir idéntico a sys2/core/rebote.py y validar 675/393/243/100 sobre 485 días.
El agente está en otra máquina (C:\Users\eulis\proyectos\open-premium-ibkr).

## ===== CÓDIGO VERBATIM reb2() (del agente, 2026-08-16) =====
def reb2(L,ks,ik,h,d,espera=12,cerca=1.0,sep=1.5,pegado=2):
    s0=(mm(h)//3)*3; i=ik.get(s0)
    if i is None: return [(h,d)]
    lado=1 if d=='C' else -1
    atrs=[L[ks[j]]['hi']-L[ks[j]]['lo'] for j in range(max(0,i-10),i+1)]
    atr=sum(atrs)/len(atrs) if atrs else 0.5
    contra=0; toco=False; cn=0
    for j in range(i+1,min(i+espera+1,len(ks))):
        x=L[ks[j]]
        if (x['cl']-x['o'])*lado<0: contra+=1
        punta=x['lo'] if lado>0 else x['hi']
        d_ac=abs(punta-x['linea']); d_cl=abs(x['cl']-x['linea'])
        if not toco and contra>=1 and d_ac<=cerca*atr: toco=True; cn=0; continue
        if toco:
            if d_cl>sep*atr:
                hh=hhmm(ks[j]); return [(hh,d)] if hh<"15:40" else []
            if d_ac<=cerca*atr:
                cn+=1
                if cn>=pegado:
                    hh=hhmm(ks[j]); return [(hh,'P' if d=='C' else 'C')] if hh<"15:40" else []
    return [] if toco else [(h,d)]

# CLAVE: toque con MECHA (punta=lo si CALL/lado>0, hi si PUT); d_ac=abs(punta-linea).
#        separacion con CIERRE: d_cl=abs(cl-linea). atr default 0.5. guard hh<"15:40".
# Caller: sp,L,ks = sen_p(bars,7,3.0); ik={k:i for i,k in enumerate(ks)}
# 2 ATR distintos: reb2 range(max(0,i-10),i+1)=11 buckets; caller range(j-9,j+1)=10 (solo p/ 'falso').
# PENDIENTE VERBATIM: st_lin_p (construye L con linea/cl/o/hi/lo/d + fu/fl), sen_p, loop llamador+grupo.

## ===== st_lin_p / sen_p / loop llamador VERBATIM (agente, 2026-08-16) =====
def st_lin_p(bars,per,mult):
    b={}
    for h,hi,lo,cl in bars:
        s=(mm(h)//3)*3
        a=b.setdefault(s,{"hi":hi,"lo":lo,"cl":cl,"o":None})
        if a["o"] is None: a["o"]=cl
        a["hi"]=max(a["hi"],hi); a["lo"]=min(a["lo"],lo); a["cl"]=cl
    ks=sorted(b)
    HI=[b[s]["hi"] for s in ks];LO=[b[s]["lo"] for s in ks];CL=[b[s]["cl"] for s in ks];OP=[b[s]["o"] for s in ks]
    tr=[];atr=[]
    for i in range(len(CL)):
        t=HI[i]-LO[i] if i==0 else max(HI[i]-LO[i],abs(HI[i]-CL[i-1]),abs(LO[i]-CL[i-1]))
        tr.append(t); atr.append(sum(tr)/len(tr) if i<per else atr[-1]+(t-atr[-1])/per)
    d=-1;fu=fl=None;out={};D=[]
    for i in range(len(ks)):
        m=(HI[i]+LO[i])/2; ub=m+mult*atr[i]; lb=m-mult*atr[i]
        if i==0: fu,fl=ub,lb
        else:
            fu=ub if (ub<fu or CL[i-1]>fu) else fu
            fl=lb if (lb>fl or CL[i-1]<fl) else fl
        if d==1 and CL[i]<fl: d=-1
        elif d==-1 and CL[i]>fu: d=1
        out[ks[i]]=dict(linea=fl if d==1 else fu,cl=CL[i],o=OP[i],hi=HI[i],lo=LO[i],d=d)
        D.append(d)
    return out,ks,D

def sen_p(bars,per,mult):
    L,ks,D=st_lin_p(bars,per,mult)
    out=[];prev=None
    for i,k in enumerate(ks):
        h=hhmm(k)
        if h<"09:30" or h>"16:00" or D[i]==0: prev=D[i]; continue
        if prev is None or D[i]!=prev: out.append((h,"C" if D[i]>0 else "P"))
        prev=D[i]
    return shift_sen(out,3), L, ks
# OJO: filtro aqui 09:30 (no 09:45); 09:45 esta en el llamador.
# OJO: prev=D[i] SE ACTUALIZA en premarket (distinto de sen_principal/flips_st3 mio).

# ---- loop llamador (clasificacion de grupo + falso) ----
# DAT=[]
# for fk,bars,rth in sesiones():
#     if fk not in P: continue
#     cl_={h:x for h,x,_,_,_ in rth}       # close por minuto RTH
#     if len(cl_)<100: continue
#     sp,L,ks=sen_p(bars,7,3.0); ik={k:i for i,k in enumerate(ks)}
#     M=P[fk]
#     flips=[(h,d) for h,d in sp if "09:45"<=h<="15:30"]
#     for i,(h,d) in enumerate(flips):
#         k=(mm(h)//3)*3; j=ik.get(k)
#         if j is None or j<10 or j+13>=len(ks): continue
#         lado=1 if d=='C' else -1
#         atr=st.mean([L[ks[z]]['hi']-L[ks[z]]['lo'] for z in range(j-9,j+1)])   # 10 buckets, SOLO p/ falso
#         if atr<=0: continue
#         fin=flips[i+1][0] if i+1<len(flips) else "15:59"
#         seg=[cl_[z] for z in sorted(cl_) if h<=z<=fin]
#         if len(seg)<3: continue
#         falso=1 if max((y-seg[0])*lado for y in seg)/atr<1.0 else 0
#         r_=reb2(L,ks,ik,h,d)
#         if not r_: grupo='DESCARTA'
#         elif r_[0][0]==h and r_[0][1]==d: grupo='NORMAL'
#         elif r_[0][1]!=d: grupo='INVIERTE'
#         else: grupo='RETRASA'
#         DAT.append({'f':fk,'h':h,'falso':falso,'grupo':grupo})

## ===== REVISION del agente de MIS 3 modulos =====
# [1] supertrend.py: RIESGO -> sen_principal != sen_p. linea debe salir de (fl if d==1 else fu)
#     DENTRO del mismo bucle que decide d. Para el rebote USAR st_lin_p verbatim.
# [2] entradas.py: descarte de aperturas usa abs(mm(sg)-mm(x)) > 5 contra TODAS las senales YA
#     presentes en S (no solo ORB); orden de llenado de S: ORB, pm_rev, v1, gap_fade, ayer_rev
#     (¡v1 ANTES que gap_fade!). El orden cambia cuales sobreviven. (yo: solo vs ORB, gap antes de v1, umbral <5)
# [3] greeks.py: CORRECTO. Detalles del motor validado:
#     - T = max(1e-6, (960 - mm(h)) / (60*24*252))  [anio 252 dias, minutos hasta 16:00]  (yo uso 365 calendario)
#     - SUELO INTRINSECO ANTES de invertir: precio = max(observado, intrinseco). 4.9% barras < intrinseco.
#       (yo devuelvo None; el motor validado CLAMPEA a intrinseco -> correccion B_suelo, +70769 vs +40638)
