# PROMPT DE RECALL — pegar esto para retomar la investigación 0DTE

Copiá y pegá este bloque en un mensaje nuevo para que Claude retome TODO el contexto:

---

Retomamos la investigación del sistema 0DTE SPY (proyecto `open-premium-ibkr`, local en `C:\Users\17862\open-premium-ibkr`).

**LEE PRIMERO Y COMPLETO el archivo `INVESTIGACION_0DTE_SISTEMA.md`** en la raíz del repo — ahí está TODO: la config final, todo lo que probamos (y qué funcionó/falló), los resultados validados en 2 años OOS, los insights del problema y los caveats. No asumas nada que no esté ahí; verifica contra el código (`simulador_st.py`) y las DBs.

Contexto ultra-resumido para que sepas de qué hablamos:
- Sistema: momentum 0DTE sobre SPY. Supertrend(7, 3.0) en velas 2-min con premarket → señales CALL/PUT. Compra el ITM más profundo que quepa en el capital. Sale por trailing 0.04% del SPY o al cierre.
- Config final ganadora: **2-min + trail 0.04% + skip apertura <09:45 + magnitud OFF + sizing FIJO $400 + banco aparte**. STOP_NEW 15:40.
- Validado 2 años (año1 tune 2025-07→2026-08, año2 OOS 2024-07→2025-07): ~+$11-12k/año por contrato, ~60% días verdes, ratio win/loss ~2.2. El edge base REPLICA OOS.
- Premium es SINTÉTICO (modelo intrínseco+extrínseco calibrado en 08-11/12/13 reales, error ~1.7-3.5%). Es el candado #1 a validar con premium real acumulado.
- Consenso del problema: los giros falsos del ST son la raíz de las pérdidas, PERO falso y verdadero son indistinguibles al entrar (intradía ≈ random walk) → el régimen NO se predice. Todo método de predicción falló. Lo que funciona: reaccionar rápido (trail ceñido) + saltar la apertura. Los días malos (~−$5k/año) son costo irreducible.
- Verificación de que nada se rompió: `python simulador_st.py` debe dar TOTAL +524.40.

Estado de descargas al momento del corte: año1 y año2 completos (DBs locales); año3 (2023-24) parcial bajando; IBKR NO tiene 1-min pre-2024 (year4/5 volvieron vacío). El tape YA NO se usa (magnitud descartada).

Decime en qué punto retomamos y seguimos desde ahí sin perder nada.

---
