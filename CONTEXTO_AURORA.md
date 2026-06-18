# CONTEXTO — Rediseño "Aurora" SMA 2.0 (para el agente del próximo chat)

> **Agente: lee esto primero.** Es el estado del rediseño en curso y qué sigue.
> Estás trabajando en este mismo worktree. Última actualización: **F6 terminada** (último commit `265bf66`). Pendientes = **Fase 4** y **Fase 5** (el usuario saltó a F6 por petición expresa).

---

## 0. Reglas del usuario (NO romper)
- **Cambios solo visuales** (CSS/HTML/layout). **NUNCA** tocar cálculos (MCP, perfiles, alpha, AEP), el mapa folium, ni los datos de los plotly.
- **Preview + aprobación** antes de dar por bueno un cambio visual. Avanzar **despacio, fase por fase**.
- **NO merge** a la carpeta real "Alfa app" ni a `main` hasta que el usuario diga **"aplica"**. Todo se queda en la rama `rediseno-aurora`.
- Conservar **toda** la funcionalidad existente.

## 1. Dónde vive el trabajo
- **Rama:** `rediseno-aurora`, **worktree:** `C:\Users\rudis\OneDrive\Escritorio\alfa-wt-f6f7` (estás aquí).
- Carpeta real "Alfa app" y `main` **INTACTAS** hasta "aplica".
- **Mockups (fuente de verdad):** `C:\Users\rudis\OneDrive\Escritorio\Nuevos diseños SMA 2.0\` — 8 PNG 2× + 8 HTML (`00_inicio - copia.html` … `07_…`).
- App: Streamlit (Python 3.14) en shell PySide6/QtWebEngine (`desktop_shell.py`).
- **Acento por fase:** Inicio #2563eb · F1 #0284c7 · F2 #0891b2 · **F3 #4f46e5 (índigo)** · F4 #7c3aed · F5 #059669 · F6 #0d9488 · F7 #d97706.

## 2. HECHO y verificado (pytest 30/30 en cada paso)

**Fundación (`navigation.py`, todas las fases):** sidebar Aurora (logo α, labels F3="Rosa y velocidad" / F5="AEP y economía", anillo progreso, main 1480px, fondo radiales del acento, Segoe UI Variable); stepper 8 pasos clicable (en Inicio va DEBAJO del hero, en fases arriba). **Franja de acento GLOBAL** (`4164d99`): `::before` con `inset:0` + `background-size:100% 4px` + `clip-path:inset(0 round 26px 26px 0 0)` → sigue la curva de las esquinas (los cards tienen `overflow:visible`, por eso no basta `height:4px`).

**Inicio (1:1 con `00_inicio`):** hero gradiente + 🏠 + líneas de viento sutiles (op .32) + 3 pills; cards reales (st.container key); Gestión con tabla HTML `.tbl` (scroll en `.home-tbl-wrap` max-height 255px, alto fijo); Config = 2 chips-expander; Importar dropzone ☁️ 138px; Fases = tiles kpi. Columnas Gestión / (Config+Importar) parejas y de alto fijo.

**Fase 1 (1:1 con `01_fase1`, `cfd2eca` + `ceb595e`):** hero cian, helpers de card-head/kpi tintado. **Esquema interactivo reconstruido desde 0** igual al mockup (flechas viento, rotor 3 aspas + torre, ROTOR→MULTIPLICADORA⚙️→GENERADOR🔌→bombilla💡, 3 cajas fórmula). **Conserva: girar según velocidad, cut-in/cut-out, Cp/energía dinámicos.**

**Fase 2 (`a85e03c` + `cc36102` + `41d6908`):** hero cian + pills. Helpers reescritos (conservan `_icon_svg` dentro del círculo tintado). **Fuente = 4 chips** (🛰️ NASA / 🌍 GWA / ⛅ Open-Meteo / 🗼 Torre; 2 fuentes reales detrás). **Diagrama de cizalladura E nuevo** (`render_cizalladura_svg` vía `components.html`: torre + 3 flechas cian a 10/50/altura + curva + fórmula). Sección E: 4 KPIs arriba + (cizalladura | banner 🎯 + 3 KPIs). **Torre meteorológica + MCP movida arriba** a col derecha debajo de B. **Gráficas F** (perfiles) activas por defecto (exp #3366ff / Log A #ff5533 / Promedio #2ca25f) + botón Consultar primary. Se respeta lo funcional: mapa folium real, plotly real (D/F/G).

**Fase 3 RECONSTRUIDA (`pages/3_Fase_3_Velocidad_promedio.py`, índigo #4f46e5; commits `c67417d`→`5d78a6e`):** hero Aurora índigo (🧭 + pills reales sectores/velocidad/dominante); card-heads y KPIs con **emoji** (helpers `_render_card_header_native`/`_render_kpi_card_native` reescritos a HTML squircle `.aur-*`, detección glifo no-ASCII o ≤2 chars→span, p.ej. badges "k"/"c"). **3 gráficas SVG** vía `components.html` (plotly intacto para reportes): `render_rosa_svg` (polar 16 cuñas degradado índigo + anillos), `render_sector_curve_svg` (Weibull índigo + Rayleigh naranja + cut-in/nominal/cut-out + ejes con números), `render_heatmap_svg` (16×bins crema→rojo) + helpers `_f3_nice_ticks`/`_f3_fmt_num`/`_sector_curve_arrays`/`_heatmap_matrix`. **Tooltips hover** restaurados (div+JS en `_f3_svg_html`; cada cuña/celda con `data-tip` → Sector/Frecuencia/Velocidad/Datos y Sector/Intervalo/Probabilidad). Sector con 4 KPIs (2×2, 68px iguales). KPIs como **card blanca** (anulado el borde gris que el `_phase_card` pinta en `.st-key-f3_skpi_*/_kpi_*`). Rosa apilada/centrada (rosa|sector parejas ~700). Decimales ES; botones índigo; inputs de cortes alineados ("Nominal (m/s)" sin `<br>`).

**F6/F7 previo (`e8e1ffe`):** exportaciones renombradas, migración DB v3 (datos ALAN/JOSE/España preservados), F6 "Estudios avanzados" con 13 módulos cableados.

## 2.b FASE 6 RECONSTRUIDA (`pages/6_Fase_6_Estudios_avanzados.py`, teal #0d9488; commits `5704fbd`→`265bf66`)
El usuario pidió saltar a F6 (orden natural era F4). 5 secciones (selector radio→**5 chips** teal vía `[role=radiogroup]`), 13 cards (`f6_card_iec…audit`).
- **Fase A** (`5704fbd`): hero teal Aurora (`.f6-hero` icono 🔬 + 3 pills 13/5/Score + wind paths); el container `f6_card_header` queda transparente. Card "Secciones" con card-head + chips. CSS base Aurora (`.aur-card-head/.aur-cicon/.aur-kpi/.aur-ki/.f6-divider/.f6-banner/.f6-fig/.f6-tbl/.f6-upload/.f6-pill/.f6-hpill`), franja teal 4px en cada card vía `::before`, botón primary teal. Helpers nuevos `_render_card_header_native/_render_kpi_card_native/_render_section_divider/_render_banner`.
- **Fase B** (`7bac5bc`): **truco clave** — redefinidos los 3 helpers compartidos (`_section_header`→card-head emoji vía mapa `_F6_ICON_EMOJI`; `_kpi_html`→grid `.f6-kgrid` de `.aur-kpi` con color por KPI en 5-tupla; `_badge_html`→banner `.f6-banner` con icono por tono) → **las 13 cards adoptan Aurora de golpe sin tocar cada call site**. KPIs IEC con rojo/ámbar/azul/teal. Gráficas IEC/terreno/clima recoloreadas a teal. `_f6_fig_layout` con `colorway` teal. Curtailment=🔌/Híbrido=🔋 editados directos (ambos eran "bolt").
- **Fases C-F** (`69eb0b3`): recoloreadas a teal las series-primarias azules (receptores turbinas, LCA donut, SCADA scatter+hist, híbrido inyectada, curtailment seg2, optim convergencia+optimizado, audit barras). Colores semánticos verde/ámbar/rojo conservados.
- **Fase G** (`265bf66`): **decimales ES** — helper `_es_num` (regex `\d[\d.,]*\d` + swap `,`↔`.` solo en tokens numéricos) aplicado a value+sub de los KPIs → "10,23 m/s"/"58.825 MWh"/"k=3,82" sin tocar "IEC 61400-1"/"ISO 14040". Eliminado bloque CSS viejo muerto.
- **GOTCHAS F6**: NO hay folium en F6 (los mapas son scatter plotly) → menos cuelgue. El preview MCP **arrastra a F5** (la app escritorio fuerza navegación); para verificar F6: clic en el ancla `a[href*=Fase_6]` y reintentar en bucle corto leyendo `.aur-card-head h2` hasta ver "Idoneidad"/"Secciones de estudio" (el `window.location.assign` también cae en F5). Cambiar de sección: clic en `input` del label del chip (no el label). Los KPIs/banners solo aparecen tras ejecutar el estudio (`if res`). Verificado en vivo: hero, 5 chips, las 5 secciones (dividers 🗺️/🌿/⚡/🎯/📋), KPIs IEC con aros de color + decimales ES + banner bad teal.

## 3. PRÓXIMO PASO  → **Fase 4** (Estelas y arreglo, acento violeta #7c3aed) y luego **Fase 5** (AEP, verde #059669)
Reconstruir `pages/4_Fase_4_Estelas_y_arreglo.py` 1:1 con `04_fase4_*` (HTML/PNG en `Nuevos diseños SMA 2.0\`), **mismo método que F2/F3**: explorar la página actual, hero Aurora + emoji + KPIs, gráficas→SVG vía `components.html` (plotly intacto para reportes), tooltips con `data-tip` donde haga falta, verificar por DOM (F4 probablemente también cuelga screenshots). Luego F5, F6, F7. Al final: tour + revisión del usuario en escritorio → con su **"aplica"** se hace el merge (la DB real migra sola a v3 al arrancar).

## 4. Método validado + GOTCHAS
- **Verificar = preview MCP** (NO PrintWindow). Config **`alfa-streamlit`, puerto 8502** en `.claude/launch.json`. `preview_start("alfa-streamlit")`; navegar con `preview_eval` `window.location.href='/Fase_3_Velocidad_promedio'`; **runOnSave OFF** → tras editar `window.location.reload()`; esperar ~16-18 s.
- **F2 cuelga los screenshots** (mapa folium) → verificar por **DOM** (`preview_eval`: getComputedStyle / getBoundingClientRect / contar elementos). Para imagen: ocultar iframe del mapa + pausar animaciones.
- **DOM de `st.container(border=True, key=K)`:** la clase `st-key-K` cae en el propio `div[data-testid="stVerticalBlock"]` (no hay BorderWrapper); padre = `stLayoutWrapper`. Estirar card a su columna: `stLayoutWrapper:has(> .st-key-K){flex:1 1 auto}`.
- **CSS global `assets/style.css`** muy específico con `!important` → para ganar, subir especificidad (`.st-key-X div[data-testid="stButton"]>button`, prefijo `#root`).
- **Patrón de fase (reusar F3-F7):** reescribir los 2 helpers `_section_title_html` y `_metric_card_html`/`_render_metric_card` para emitir card-head/kpi conservando el `_icon_svg` dentro del contenedor tintado; color `--kc` desde `tone`/`icon_variant`. Hero con pills+viento. Look de card por `[class*="st-key-fN_card_"]`. Diagramas estrella (esquema/cizalladura/rosa) se RECONSTRUYEN como el mockup conservando funciones, vía `components.html`.
- **Mover bloques con lógica:** script python por rango de líneas, cuidar indentación y scope (no caer dentro de un `if`/`try`), `py_compile` + pytest + verificar por DOM.
- **Tests:** `python -m pytest tests/` → mantener **30/30** (smoke AppTest por página).
- **GOTCHAS F3 (aplican a F4-F7):** (a) F3 **también cuelga los screenshots** (5 iframes SVG + heatmap 800 celdas) → verificar SIEMPRE por DOM, leyendo dentro de iframes con `iframe.contentDocument`. (b) **`serverId` del preview exacto** — usar `preview_list` (un id equivocado igual devuelve "reloading"). (c) **CSS viejo con alturas fijas** (`height:600px` en cards, etc.) puede dejar hueco con los SVG nuevos → anularlo (`height:auto;min-height:0`). (d) El `_phase_card(border=True)` pinta su **borde gris (8px) en el propio `.st-key-K`** (NO en un BorderWrapper) → para que se vea solo tu `.aur-kpi`, anular border/bg/shadow/padding/radius en `.st-key-K`. (e) **Tooltips en SVG**: patrón reutilizable — div `#tip` + JS `mousemove→closest('[data-tip]')` dentro de `components.html`, y `data-tip="...&#10;..."` por elemento. (f) Aspecto del viewBox debe casar con el alto del iframe o hay **letterbox** (curva "flotando"). (g) El usuario debe **REFRESCAR la app de escritorio** (tecla R / reiniciar; `runOnSave` off) para ver los commits.

## 5. Commits de la rama (reciente arriba)
```
5d78a6e F3 - KPIs como card blanca (anulado borde gris del _phase_card en .st-key-f3_skpi/_kpi), sector 2×2 a 68px iguales, etiqueta 'Nominal (m/s)' sin <br> → inputs cortes alineados
ec6a201 F3 - tooltips hover en rosa (Sector/Frecuencia/Velocidad/Datos) y heatmap (Sector/Intervalo/Probabilidad) vía data-tip+JS en el SVG; conserva la funcionalidad del plotly
3af6ff4 F3 alineación - KPIs strip parejos (94px), anular height:600 fijo viejo, curva sector llena (viewBox 700×440), rosa apilada/centrada (rosa|sector 704/697)
f6c6fad F3 fase D - decimales ES (43.848/10,23/0,1465), KPIs sector 2×2 sin texto cortado, curva 440, botones índigo, rosa centrada
ba66b65 F3 fase C - sector con 4 KPIs del mockup (Frecuencia/Horas-año/k/c, badges de letra k/c)
8c5d009 F3 fase B - rosa/sector/heatmap como SVG (render_rosa_svg polar / render_sector_curve_svg / render_heatmap_svg; plotly intacto para reportes)
c67417d F3 fase A - hero Aurora índigo + card-heads/KPIs emoji+subtítulo (helpers _render_card_header_native/_render_kpi_card_native reescritos)
500a6c7 F2 ronda3 - quitar banner α (heterogeneidad), compactar dropzone B (icono 58), limpiar Torre M (sin split), mapa 658 (A_gap 0)
ab025de F2 ronda2 - números (ticks+puntos) en F/G, D como SVG (render_serie_horaria_svg), E balanceada (cizalladura 330), Torre 2 KPIs (Recovery/MCP R²), mapa 672
0224798 F2 reconstrucción - gráficas F/G como SVG del mockup (render_perfil_fig_svg/render_comparacion_fig_svg), iconos emoji, fila A/B/M simétrica (mapa 590)
5b3e5c0 F2 paridad - 3a línea (subtítulo) en KPIs C+E + card-head 'Fuente de datos' envolviendo los chips
7c332dc F2 más fiel - iconos card-head (pin/nube/torre +icono SVG tower), columnas A/B parejas [1,1], mapa 300px, banner verde
41d6908 F2 - Torre+MCP arriba (col B), gráficas F visibles, botón primary
cc36102 F2 más fiel - fuente como chips + diagrama de cizalladura E
4164d99 fix: franja de acento sigue el contorno redondeado (GLOBAL)
ceb595e F1: reconstruir el esquema interactivo igual al mockup
651eb44 fix: franja de Inicio no asoma en esquinas
d178961 fix: pulido fino de Inicio
a85e03c F2: paridad base   ·   cfd2eca F1: paridad 1:1
3824b68 / bb47e7d  Inicio paridad + cards/columnas
5a87b9f / 5e893b4 / 053d4a5 / e8e1ffe  fundación + F6/F7
```

## 6. Memoria persistente
El chat nuevo carga `MEMORY.md` automáticamente; detalle vivo en `memory/aurora-redesign.md`. Hay copia humana en `Escritorio\RESUMEN_REDISENO_AURORA.md`. **Este archivo (`CONTEXTO_AURORA.md`) vive en la raíz del worktree** para que el agente lo tenga junto al código.
