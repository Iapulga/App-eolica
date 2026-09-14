"""Textos del reporte bankable en español, inglés, portugués y francés.

Cada clave guarda una tupla (es, en, pt, fr); las cadenas pueden llevar campos {nombre} que se
rellenan con los datos del proyecto al llamar a `tr(clave, lang, nombre=valor)`. Una cadena
simple (no tupla) vale igual para los cuatro idiomas.
"""
from __future__ import annotations

IDIOMAS = ("es", "en", "pt", "fr")
_IDX = {codigo: i for i, codigo in enumerate(IDIOMAS)}

_T: dict = {}

# ── Portada, control del documento e índice ──
_T.update({
    "titulo": ("INFORME BANKABLE", "BANKABLE REPORT", "RELATÓRIO BANCÁVEL", "RAPPORT BANCABLE"),
    "titulo_corto": ("Informe bankable", "Bankable report", "Relatório bancável", "Rapport bancable"),
    "subtitulo": ("Evaluación técnico-económica de un proyecto eólico",
                  "Technical and economic assessment of a wind project",
                  "Avaliação técnico-econômica de um projeto eólico",
                  "Évaluation technico-économique d'un projet éolien"),
    "campo": ("Campo", "Field", "Campo", "Champ"),
    "valor": ("Valor", "Value", "Valor", "Valeur"),
    "indicador": ("Indicador", "Indicator", "Indicador", "Indicateur"),
    "cliente": ("Cliente", "Client", "Cliente", "Client"),
    "autor": ("Autor", "Author", "Autor", "Auteur"),
    "pais": ("País", "Country", "País", "Pays"),
    "coordenadas": ("Coordenadas (lat, lon)", "Coordinates (lat, lon)", "Coordenadas (lat, lon)", "Coordonnées (lat, lon)"),
    "fecha": ("Fecha", "Date", "Data", "Date"),
    "codigo_doc": ("Código del documento", "Document code", "Código do documento", "Code du document"),
    "revision": ("Revisión", "Revision", "Revisão", "Révision"),
    "version_sma": ("Versión de SMA", "SMA version", "Versão do SMA", "Version de SMA"),
    "aviso_t": ("AVISO", "DISCLAIMER", "AVISO LEGAL", "AVERTISSEMENT"),
    "aviso_b": (
        "Este informe lo genera automáticamente SMA 2.0, una herramienta de prefactibilidad, con los datos del "
        "proyecto configurados en la aplicación. No sustituye una evaluación de producción energética (EYA) de "
        "tercera parte ni una certificación (DNV, UL, TÜV). Para decisiones de inversión o de financiación de "
        "proyecto, los resultados deben ser validados por un consultor independiente.",
        "This report is generated automatically by SMA 2.0, a pre-feasibility tool, from the project data "
        "configured in the application. It does not replace a third-party energy yield assessment (EYA) or a "
        "certification (DNV, UL, TÜV). For investment or project-finance decisions, the results must be "
        "validated by an independent consultant.",
        "Este relatório é gerado automaticamente pelo SMA 2.0, uma ferramenta de pré-viabilidade, com os dados "
        "do projeto configurados no aplicativo. Não substitui uma avaliação de produção energética (EYA) de "
        "terceira parte nem uma certificação (DNV, UL, TÜV). Para decisões de investimento ou de project finance, "
        "os resultados devem ser validados por um consultor independente.",
        "Ce rapport est généré automatiquement par SMA 2.0, un outil de préfaisabilité, à partir des données du "
        "projet configurées dans l'application. Il ne remplace ni une évaluation du productible (EYA) réalisée "
        "par un tiers ni une certification (DNV, UL, TÜV). Pour toute décision d'investissement ou de "
        "financement de projet, les résultats doivent être validés par un consultant indépendant.",
    ),
    "control_doc": ("Control del documento", "Document control", "Controle do documento", "Suivi du document"),
    "control_intro": ("Historial de revisiones del documento.", "Document revision history.",
                      "Histórico de revisões do documento.", "Historique des révisions du document."),
    "rev": ("Rev.", "Rev.", "Rev.", "Rév."),
    "preparado": ("Preparado por", "Prepared by", "Preparado por", "Préparé par"),
    "revisado": ("Revisado por", "Checked by", "Revisado por", "Vérifié par"),
    "notas": ("Notas", "Notes", "Notas", "Notes"),
    "rev_nota": ("Versión inicial generada automáticamente por SMA 2.0",
                 "Initial version generated automatically by SMA 2.0",
                 "Versão inicial gerada automaticamente pelo SMA 2.0",
                 "Version initiale générée automatiquement par SMA 2.0"),
    "toc": ("Tabla de contenido", "Table of contents", "Sumário", "Table des matières"),
    "toc_placeholder": ("El índice se completa automáticamente al abrir el documento en Word.",
                        "The table of contents is filled in automatically when the document is opened in Word.",
                        "O sumário é preenchido automaticamente ao abrir o documento no Word.",
                        "La table des matières se remplit automatiquement à l'ouverture du document dans Word."),
    "pagina": ("Página", "Page", "Página", "Page"),
    "de": ("de", "of", "de", "sur"),
    "figura": ("Figura", "Figure", "Figura", "Figure"),
    "tabla": ("Tabla", "Table", "Tabela", "Tableau"),
    "si": ("Sí", "Yes", "Sim", "Oui"),
    "no": ("No", "No", "Não", "Non"),
    "anios": ("años", "years", "anos", "ans"),
    "mwh_anio": ("MWh/año", "MWh/yr", "MWh/ano", "MWh/an"),
    "h_anio": ("h/año", "h/yr", "h/ano", "h/an"),
    "no_disponible": ("No disponible", "Not available", "Não disponível", "Non disponible"),
    "no_calculado": ("No calculado", "Not calculated", "Não calculado", "Non calculé"),
    "no_evaluado": ("No evaluado", "Not assessed", "Não avaliado", "Non évalué"),
    "cumple": ("Cumple", "Complies", "Atende", "Conforme"),
    "no_cumple": ("No cumple", "Does not comply", "Não atende", "Non conforme"),
    "sin_datos": ("Sin datos", "No data", "Sem dados", "Pas de données"),
    "informativo": ("Informativo", "For information", "Informativo", "Informatif"),
    "total": "Total",
    "curva_fase1": ("Curva de potencia definida en la Fase 1", "Power curve defined in Phase 1",
                    "Curva de potência definida na Fase 1", "Courbe de puissance définie en Phase 1"),
})

# ── Títulos de sección ──
_T.update({
    "s1": ("1. Resumen ejecutivo", "1. Executive summary", "1. Resumo executivo", "1. Résumé exécutif"),
    "s1_1": ("1.1 Hallazgos clave", "1.1 Key findings", "1.1 Principais constatações", "1.1 Constats clés"),
    "s2": ("2. Descripción del proyecto", "2. Project description", "2. Descrição do projeto", "2. Description du projet"),
    "s2_1": ("2.1 Localización del sitio", "2.1 Site location", "2.1 Localização do sítio", "2.1 Localisation du site"),
    "s2_2": ("2.2 Aerogenerador", "2.2 Wind turbine", "2.2 Aerogerador", "2.2 Éolienne"),
    "s2_3": ("2.3 Disposición del parque", "2.3 Wind farm layout", "2.3 Layout do parque", "2.3 Implantation du parc"),
    "s3": ("3. Recurso eólico", "3. Wind resource", "3. Recurso eólico", "3. Ressource éolienne"),
    "s3_1": ("3.1 Fuente y periodo de datos", "3.1 Data source and period", "3.1 Fonte e período dos dados",
             "3.1 Source et période des données"),
    "s3_2": ("3.2 Perfil vertical y extrapolación a la altura del buje",
             "3.2 Vertical profile and extrapolation to hub height",
             "3.2 Perfil vertical e extrapolação à altura do cubo",
             "3.2 Profil vertical et extrapolation à la hauteur du moyeu"),
    "s3_3": ("3.3 Turbulencia y densidad del aire", "3.3 Turbulence and air density",
             "3.3 Turbulência e densidade do ar", "3.3 Turbulence et densité de l'air"),
    "s3_4": ("3.4 Distribución por sectores de dirección", "3.4 Distribution by direction sector",
             "3.4 Distribuição por setores de direção", "3.4 Répartition par secteur de direction"),
    "s4": ("4. Producción de energía", "4. Energy yield", "4. Produção de energia", "4. Production d'énergie"),
    "s4_1": ("4.1 Cascada de pérdidas", "4.1 Loss cascade", "4.1 Cascata de perdas", "4.1 Cascade des pertes"),
    "s4_2": ("4.2 Resumen energético y factor de planta", "4.2 Energy summary and capacity factor",
             "4.2 Resumo energético e fator de capacidade", "4.2 Bilan énergétique et facteur de charge"),
    "s4_3": ("4.3 Energía por sector de dirección", "4.3 Energy by direction sector",
             "4.3 Energia por setor de direção", "4.3 Énergie par secteur de direction"),
    "s4_4": ("4.4 Producción por aerogenerador", "4.4 Production per wind turbine",
             "4.4 Produção por aerogerador", "4.4 Production par éolienne"),
    "s5": ("5. Incertidumbre y probabilidades de excedencia", "5. Uncertainty and exceedance probabilities",
           "5. Incerteza e probabilidades de excedência", "5. Incertitude et probabilités de dépassement"),
    "s5_1": ("5.1 Componentes de la incertidumbre", "5.1 Uncertainty components",
             "5.1 Componentes da incerteza", "5.1 Composantes de l'incertitude"),
    "s5_2": ("5.2 Resultado del Monte Carlo", "5.2 Monte Carlo result", "5.2 Resultado do Monte Carlo",
             "5.2 Résultat du Monte Carlo"),
    "s5_gen": ("5.1 Estimación genérica", "5.1 Generic estimate", "5.1 Estimativa genérica", "5.1 Estimation générique"),
    "s6": ("6. Idoneidad del sitio (IEC 61400-1)", "6. Site suitability (IEC 61400-1)",
           "6. Adequação do sítio (IEC 61400-1)", "6. Adéquation du site (CEI 61400-1)"),
    "s7": ("7. Aspectos ambientales", "7. Environmental aspects", "7. Aspectos ambientais", "7. Aspects environnementaux"),
    "s7_1": ("7.1 Ruido", "7.1 Noise", "7.1 Ruído", "7.1 Bruit"),
    "s7_2": ("7.2 Parpadeo de sombra (shadow flicker)", "7.2 Shadow flicker",
             "7.2 Cintilação de sombra (shadow flicker)", "7.2 Ombres portées (shadow flicker)"),
    "s7_3": ("7.3 Otros aspectos a evaluar", "7.3 Other aspects to assess", "7.3 Outros aspectos a avaliar",
             "7.3 Autres aspects à évaluer"),
    "s8": ("8. Análisis económico", "8. Economic analysis", "8. Análise econômica", "8. Analyse économique"),
    "s8_1": ("8.1 Supuestos económicos", "8.1 Economic assumptions", "8.1 Premissas econômicas",
             "8.1 Hypothèses économiques"),
    "s8_2": ("8.2 Inversión (CAPEX)", "8.2 Investment (CAPEX)", "8.2 Investimento (CAPEX)", "8.2 Investissement (CAPEX)"),
    "s8_3": ("8.3 Costos de operación (OPEX)", "8.3 Operating costs (OPEX)", "8.3 Custos de operação (OPEX)",
             "8.3 Coûts d'exploitation (OPEX)"),
    "s8_4": ("8.4 Indicadores financieros", "8.4 Financial indicators", "8.4 Indicadores financeiros",
             "8.4 Indicateurs financiers"),
    "s8_5": ("8.5 Flujo de caja", "8.5 Cash flow", "8.5 Fluxo de caixa", "8.5 Flux de trésorerie"),
    "s8_6": ("8.6 Análisis de sensibilidad", "8.6 Sensitivity analysis", "8.6 Análise de sensibilidade",
             "8.6 Analyse de sensibilité"),
    "s8_7": ("8.7 Marco regulatorio del país", "8.7 Country regulatory framework", "8.7 Marco regulatório do país",
             "8.7 Cadre réglementaire du pays"),
    "s8_8": ("8.8 Lista de verificación normativa", "8.8 Standards checklist", "8.8 Lista de verificação normativa",
             "8.8 Liste de contrôle normative"),
    "s9": ("9. Registro de riesgos", "9. Risk register", "9. Registro de riscos", "9. Registre des risques"),
    "s10": ("10. Conclusiones y recomendaciones", "10. Conclusions and recommendations",
            "10. Conclusões e recomendações", "10. Conclusions et recommandations"),
    "s11": ("11. Apéndices", "11. Appendices", "11. Apêndices", "11. Annexes"),
    "s11_a": ("A. Metodología aplicada", "A. Methodology applied", "A. Metodologia aplicada", "A. Méthodologie appliquée"),
    "s11_b": ("B. Validación de los modelos", "B. Model validation", "B. Validação dos modelos", "B. Validation des modèles"),
    "s11_c": ("C. Glosario", "C. Glossary", "C. Glossário", "C. Glossaire"),
    "s11_d": ("D. Referencias", "D. References", "D. Referências", "D. Références"),
    "s11_e": ("E. Limitaciones y exclusiones", "E. Limitations and exclusions", "E. Limitações e exclusões",
              "E. Limites et exclusions"),
})

# ── Resumen ejecutivo: veredicto, indicadores y hallazgos ──
_T.update({
    "ver_nd_t": ("Veredicto preliminar: NO DETERMINADO", "Preliminary verdict: NOT DETERMINED",
                 "Parecer preliminar: NÃO DETERMINADO", "Avis préliminaire : NON DÉTERMINÉ"),
    "ver_nd_b": ("Faltan los resultados económicos de la Fase 5 (VPN y TIR). Complete la Fase 5 y vuelva a generar el informe.",
                 "The Phase 5 economic results (NPV and IRR) are missing. Complete Phase 5 and generate the report again.",
                 "Faltam os resultados econômicos da Fase 5 (VPL e TIR). Conclua a Fase 5 e gere o relatório novamente.",
                 "Les résultats économiques de la Phase 5 (VAN et TRI) sont manquants. Terminez la Phase 5 et "
                 "générez à nouveau le rapport."),
    "ver_nc_t": ("Veredicto preliminar: NO CONCLUYENTE", "Preliminary verdict: INCONCLUSIVE",
                 "Parecer preliminar: INCONCLUSIVO", "Avis préliminaire : NON CONCLUANT"),
    "ver_nc_b": ("Los costos o el precio de la energía están fuera de los rangos habituales (ver avisos). Los indicadores "
                 "financieros (VPN {npv}, TIR {irr}) no son representativos hasta revisar la moneda y los valores de la Fase 5.",
                 "Costs or the energy price are outside the usual ranges (see warnings). The financial indicators "
                 "(NPV {npv}, IRR {irr}) are not representative until the currency and the Phase 5 values are reviewed.",
                 "Os custos ou o preço da energia estão fora das faixas habituais (ver avisos). Os indicadores "
                 "financeiros (VPL {npv}, TIR {irr}) não são representativos até revisar a moeda e os valores da Fase 5.",
                 "Les coûts ou le prix de l'énergie sont hors des plages habituelles (voir les avertissements). Les "
                 "indicateurs financiers (VAN {npv}, TRI {irr}) ne sont pas représentatifs tant que la devise et les "
                 "valeurs de la Phase 5 n'ont pas été vérifiées."),
    "ver_ok_t": ("Veredicto preliminar: ATRACTIVO para avanzar hacia la financiación",
                 "Preliminary verdict: ATTRACTIVE to move towards financing",
                 "Parecer preliminar: ATRATIVO para avançar rumo ao financiamento",
                 "Avis préliminaire : ATTRACTIF pour avancer vers le financement"),
    "ver_ok_b": ("La TIR del caso base ({irr}) supera el WACC típico de {pais} ({wacc}) y el VPN es positivo ({npv}). "
                 "Sujeto a la validación independiente de la AEP y del P90 y a la confirmación de los supuestos de "
                 "precio, disponibilidad y O&M.",
                 "The base-case IRR ({irr}) exceeds the typical WACC in {pais} ({wacc}) and the NPV is positive ({npv}). "
                 "Subject to independent validation of the AEP and P90 and to confirmation of the price, availability "
                 "and O&M assumptions.",
                 "A TIR do caso base ({irr}) supera o WACC típico de {pais} ({wacc}) e o VPL é positivo ({npv}). "
                 "Sujeito à validação independente da AEP e do P90 e à confirmação das premissas de preço, "
                 "disponibilidade e O&M.",
                 "Le TRI du cas de base ({irr}) dépasse le WACC typique de {pais} ({wacc}) et la VAN est positive "
                 "({npv}). Sous réserve de la validation indépendante de l'AEP et du P90 et de la confirmation des "
                 "hypothèses de prix, de disponibilité et d'exploitation-maintenance."),
    "ver_it_t": ("Veredicto preliminar: REQUIERE ITERACIÓN", "Preliminary verdict: REQUIRES ITERATION",
                 "Parecer preliminar: REQUER ITERAÇÃO", "Avis préliminaire : ITÉRATION NÉCESSAIRE"),
    "ver_it_b": ("La TIR del caso base ({irr}) no supera el WACC típico de {pais} ({wacc}) o el VPN ({npv}) no es "
                 "positivo. Conviene iterar el precio de venta, la disposición, el aerogenerador o los costos antes de "
                 "presentar el proyecto a financiadores.",
                 "The base-case IRR ({irr}) does not exceed the typical WACC in {pais} ({wacc}) or the NPV ({npv}) is "
                 "not positive. The sale price, layout, turbine or costs should be iterated before presenting the "
                 "project to lenders.",
                 "A TIR do caso base ({irr}) não supera o WACC típico de {pais} ({wacc}) ou o VPL ({npv}) não é "
                 "positivo. Convém iterar o preço de venda, o layout, o aerogerador ou os custos antes de apresentar "
                 "o projeto a financiadores.",
                 "Le TRI du cas de base ({irr}) ne dépasse pas le WACC typique de {pais} ({wacc}) ou la VAN ({npv}) "
                 "n'est pas positive. Il convient d'itérer le prix de vente, l'implantation, l'éolienne ou les coûts "
                 "avant de présenter le projet aux prêteurs."),
    "avisos_t": ("Avisos de coherencia de los datos", "Data consistency warnings", "Avisos de coerência dos dados",
                 "Avertissements de cohérence des données"),
    "k_capacidad": ("Capacidad instalada", "Installed capacity", "Capacidade instalada", "Puissance installée"),
    "k_turbina": ("Aerogenerador", "Wind turbine", "Aerogerador", "Éolienne"),
    "k_v_buje": ("Velocidad media a la altura del buje", "Mean wind speed at hub height",
                 "Velocidade média à altura do cubo", "Vitesse moyenne à la hauteur du moyeu"),
    "k_aep_bruta": ("AEP bruta", "Gross AEP", "AEP bruta", "AEP brute"),
    "k_aep_estela": ("AEP tras estelas", "AEP after wakes", "AEP após esteiras", "AEP après sillages"),
    "k_aep_neta": ("AEP neta (Fase 5)", "Net AEP (Phase 5)", "AEP líquida (Fase 5)", "AEP nette (Phase 5)"),
    "k_p50": "AEP P50",
    "k_p75": "AEP P75",
    "k_p90": ("AEP P90 (referencia bancaria)", "AEP P90 (banking reference)", "AEP P90 (referência bancária)",
              "AEP P90 (référence bancaire)"),
    "k_p99": "AEP P99",
    "k_fp_neto": ("Factor de planta neto", "Net capacity factor", "Fator de capacidade líquido", "Facteur de charge net"),
    "k_fp_bruto": ("Factor de planta bruto", "Gross capacity factor", "Fator de capacidade bruto", "Facteur de charge brut"),
    "k_lcoe": "LCOE",
    "k_npv": ("VPN", "NPV", "VPL", "VAN"),
    "k_irr": ("TIR", "IRR", "TIR", "TRI"),
    "k_wacc": ("WACC típico del país", "Typical country WACC", "WACC típico do país", "WACC typique du pays"),
    "k_payback_s": ("Periodo de recuperación simple", "Simple payback period", "Período de retorno simples",
                    "Délai de récupération simple"),
    "k_payback_d": ("Periodo de recuperación descontado", "Discounted payback period", "Período de retorno descontado",
                    "Délai de récupération actualisé"),
    "k_capex": ("CAPEX total", "Total CAPEX", "CAPEX total", "CAPEX total"),
    "k_opex": ("OPEX anual", "Annual OPEX", "OPEX anual", "OPEX annuel"),
    "h_recurso": ("Recurso: velocidad media de {v} m/s a {h} m (serie {fuente}, {inicio} → {fin}); extrapolación "
                  "vertical: {modelo}.",
                  "Resource: mean wind speed of {v} m/s at {h} m ({fuente} series, {inicio} → {fin}); vertical "
                  "extrapolation: {modelo}.",
                  "Recurso: velocidade média de {v} m/s a {h} m (série {fuente}, {inicio} → {fin}); extrapolação "
                  "vertical: {modelo}.",
                  "Ressource : vitesse moyenne de {v} m/s à {h} m (série {fuente}, {inicio} → {fin}) ; extrapolation "
                  "verticale : {modelo}."),
    "h_estela": ("Estelas: pérdida aplicada de {pct} ({mwh} MWh/año), modo «{modo}».",
                 "Wakes: applied loss of {pct} ({mwh} MWh/yr), “{modo}” mode.",
                 "Esteiras: perda aplicada de {pct} ({mwh} MWh/ano), modo «{modo}».",
                 "Sillages : perte appliquée de {pct} ({mwh} MWh/an), mode « {modo} »."),
    "h_estela_f4": (" En la Fase 4, el sector más afectado es {sector} ({pct}).",
                    " In Phase 4, the most affected sector is {sector} ({pct}).",
                    " Na Fase 4, o setor mais afetado é {sector} ({pct}).",
                    " En Phase 4, le secteur le plus affecté est {sector} ({pct})."),
    "h_perdidas": ("Pérdida total de la AEP bruta a la neta: {pct}; factor de planta neto {fp}.",
                   "Total loss from gross to net AEP: {pct}; net capacity factor {fp}.",
                   "Perda total da AEP bruta para a líquida: {pct}; fator de capacidade líquido {fp}.",
                   "Perte totale de l'AEP brute à l'AEP nette : {pct} ; facteur de charge net {fp}."),
    "h_mc": ("Incertidumbre: P90 = {p90} MWh/año ({ratio} del P50); coeficiente de variación de {cv} con {n} muestras "
             "de Monte Carlo.",
             "Uncertainty: P90 = {p90} MWh/yr ({ratio} of P50); coefficient of variation of {cv} from {n} Monte Carlo "
             "samples.",
             "Incerteza: P90 = {p90} MWh/ano ({ratio} do P50); coeficiente de variação de {cv} com {n} amostras de "
             "Monte Carlo.",
             "Incertitude : P90 = {p90} MWh/an ({ratio} du P50) ; coefficient de variation de {cv} sur {n} tirages "
             "Monte Carlo."),
    "h_mc_gen": ("Incertidumbre: sin Monte Carlo en la Fase 5; P90 ≈ {p90} MWh/año con una σ genérica de {cv}.",
                 "Uncertainty: no Monte Carlo in Phase 5; P90 ≈ {p90} MWh/yr with a generic σ of {cv}.",
                 "Incerteza: sem Monte Carlo na Fase 5; P90 ≈ {p90} MWh/ano com uma σ genérica de {cv}.",
                 "Incertitude : pas de Monte Carlo en Phase 5 ; P90 ≈ {p90} MWh/an avec un σ générique de {cv}."),
    "h_iec": ("IEC 61400-1: clase declarada {clase}/{cat}; velocidad media de {v} m/s frente a {lim} m/s y TI a "
              "15 m/s de {ti} (indicativa) frente a {ti_lim} → {res}.",
              "IEC 61400-1: declared class {clase}/{cat}; mean speed of {v} m/s vs {lim} m/s and TI at 15 m/s of "
              "{ti} (indicative) vs {ti_lim} → {res}.",
              "IEC 61400-1: classe declarada {clase}/{cat}; velocidade média de {v} m/s frente a {lim} m/s e TI a "
              "15 m/s de {ti} (indicativa) frente a {ti_lim} → {res}.",
              "CEI 61400-1 : classe déclarée {clase}/{cat} ; vitesse moyenne de {v} m/s pour {lim} m/s et TI à "
              "15 m/s de {ti} (indicative) pour {ti_lim} → {res}."),
    "h_ruido": ("Ruido: nivel máximo en receptores de {db} dB(A) frente a límites de {dia}/{noche} dB(A) (día/noche).",
                "Noise: maximum level at receptors of {db} dB(A) vs limits of {dia}/{noche} dB(A) (day/night).",
                "Ruído: nível máximo nos receptores de {db} dB(A) frente a limites de {dia}/{noche} dB(A) (dia/noite).",
                "Bruit : niveau maximal aux récepteurs de {db} dB(A) pour des limites de {dia}/{noche} dB(A) "
                "(jour/nuit)."),
    "h_flicker": ("Parpadeo de sombra: máximo de {h} h/año frente a un límite de {lim} h/año.",
                  "Shadow flicker: maximum of {h} h/yr vs a limit of {lim} h/yr.",
                  "Cintilação de sombra: máximo de {h} h/ano frente a um limite de {lim} h/ano.",
                  "Ombres portées : maximum de {h} h/an pour une limite de {lim} h/an."),
    "h_amb_no": ("Ruido y parpadeo de sombra: no evaluados en la Fase 6.",
                 "Noise and shadow flicker: not assessed in Phase 6.",
                 "Ruído e cintilação de sombra: não avaliados na Fase 6.",
                 "Bruit et ombres portées : non évalués en Phase 6."),
    "h_eco": ("Economía: VPN de {npv} y TIR de {irr} con un precio de {precio} y una tasa de descuento de {tasa}.",
              "Economics: NPV of {npv} and IRR of {irr} with a price of {precio} and a discount rate of {tasa}.",
              "Economia: VPL de {npv} e TIR de {irr} com preço de {precio} e taxa de desconto de {tasa}.",
              "Économie : VAN de {npv} et TRI de {irr} avec un prix de {precio} et un taux d'actualisation de {tasa}."),
})

# ── 2. Proyecto: sitio, aerogenerador y disposición ──
_T.update({
    "latitud": ("Latitud", "Latitude", "Latitude", "Latitude"),
    "longitud": ("Longitud", "Longitude", "Longitude", "Longitude"),
    "pais_informe": ("País del informe", "Report country", "País do relatório", "Pays du rapport"),
    "pais_coord": ("País según las coordenadas", "Country from the coordinates", "País segundo as coordenadas",
                   "Pays d'après les coordonnées"),
    "fuente_datos": ("Fuente de datos de viento", "Wind data source", "Fonte dos dados de vento",
                     "Source des données de vent"),
    "periodo": ("Periodo analizado", "Period analysed", "Período analisado", "Période analysée"),
    "altitud": ("Altitud del sitio sobre el nivel del mar", "Site elevation above sea level",
                "Altitude do sítio acima do nível do mar", "Altitude du site au-dessus du niveau de la mer"),
    "temperatura": ("Temperatura media anual", "Mean annual temperature", "Temperatura média anual",
                    "Température moyenne annuelle"),
    "densidad_sitio": ("Densidad del aire en el sitio", "Site air density", "Densidade do ar no sítio",
                       "Densité de l'air sur le site"),
    "modelo": ("Modelo", "Model", "Modelo", "Modèle"),
    "diametro": ("Diámetro del rotor", "Rotor diameter", "Diâmetro do rotor", "Diamètre du rotor"),
    "area": ("Área barrida", "Swept area", "Área varrida", "Surface balayée"),
    "altura_buje": ("Altura del buje", "Hub height", "Altura do cubo", "Hauteur du moyeu"),
    "p_nominal": ("Potencia nominal por aerogenerador", "Rated power per turbine", "Potência nominal por aerogerador",
                  "Puissance nominale par éolienne"),
    "n_aero": ("Número de aerogeneradores", "Number of wind turbines", "Número de aerogeradores", "Nombre d'éoliennes"),
    "cut_in": ("Velocidad de arranque (cut-in)", "Cut-in wind speed", "Velocidade de partida (cut-in)",
               "Vitesse de démarrage (cut-in)"),
    "v_nominal": ("Velocidad nominal", "Rated wind speed", "Velocidade nominal", "Vitesse nominale"),
    "cut_out": ("Velocidad de parada (cut-out)", "Cut-out wind speed", "Velocidade de corte (cut-out)",
                "Vitesse de coupure (cut-out)"),
    "ct": ("Coeficiente de empuje (Ct) representativo", "Representative thrust coefficient (Ct)",
           "Coeficiente de empuxo (Ct) representativo", "Coefficient de poussée (Ct) représentatif"),
    "dens_curva": ("Densidad de referencia de la curva", "Power curve reference density",
                   "Densidade de referência da curva", "Densité de référence de la courbe"),
    "turbina_intro": ("Datos del aerogenerador tomados de la curva de potencia y la geometría configuradas en la Fase 1.",
                      "Turbine data taken from the power curve and geometry configured in Phase 1.",
                      "Dados do aerogerador obtidos da curva de potência e da geometria configuradas na Fase 1.",
                      "Données de l'éolienne issues de la courbe de puissance et de la géométrie configurées en Phase 1."),
    "cap_curva": ("Curva de potencia del aerogenerador.", "Wind turbine power curve.",
                  "Curva de potência do aerogerador.", "Courbe de puissance de l'éolienne."),
    "layout_tipo": ("Tipo de disposición: {tipo}.", "Layout type: {tipo}.", "Tipo de layout: {tipo}.",
                    "Type d'implantation : {tipo}."),
    "layout_sep": (" Separación entre aerogeneradores: {dx} D × {dy} D.", " Turbine spacing: {dx} D × {dy} D.",
                   " Espaçamento entre aerogeradores: {dx} D × {dy} D.", " Espacement des éoliennes : {dx} D × {dy} D."),
    "layout_no": ("La disposición del parque no está disponible (configúrela en la Fase 4).",
                  "The wind farm layout is not available (configure it in Phase 4).",
                  "O layout do parque não está disponível (configure-o na Fase 4).",
                  "L'implantation du parc n'est pas disponible (configurez-la en Phase 4)."),
    "turbina_col": ("Aerogenerador", "Turbine", "Aerogerador", "Éolienne"),
    "cap_layout": ("Disposición del parque: {n} aerogeneradores, rotor de {d} m (círculos a escala).",
                   "Wind farm layout: {n} turbines, {d} m rotor (circles to scale).",
                   "Layout do parque: {n} aerogeradores, rotor de {d} m (círculos em escala).",
                   "Implantation du parc : {n} éoliennes, rotor de {d} m (cercles à l'échelle)."),
})

# ── 3. Recurso eólico ──
_T.update({
    "cap_rosa": ("Rosa de vientos: frecuencia por sector de dirección ({serie}).",
                 "Wind rose: frequency by direction sector ({serie}).",
                 "Rosa dos ventos: frequência por setor de direção ({serie}).",
                 "Rose des vents : fréquence par secteur de direction ({serie})."),
    "cap_hist": ("Distribución de velocidades ({serie}) y ajuste de Weibull.",
                 "Wind speed distribution ({serie}) and Weibull fit.",
                 "Distribuição de velocidades ({serie}) e ajuste de Weibull.",
                 "Distribution des vitesses ({serie}) et ajustement de Weibull."),
    "serie_buje": ("serie a la altura del buje, {h} m", "hub-height series, {h} m", "série à altura do cubo, {h} m",
                   "série à la hauteur du moyeu, {h} m"),
    "serie_ref": ("serie de referencia a {h} m", "reference series at {h} m", "série de referência a {h} m",
                  "série de référence à {h} m"),
    "altura_ref": ("Altura de referencia de los datos", "Data reference height", "Altura de referência dos dados",
                   "Hauteur de référence des données"),
    "serie_usada": ("Serie utilizada", "Series used", "Série utilizada", "Série utilisée"),
    "serie_nasa": ("Satelital / reanálisis", "Satellite / reanalysis", "Satélite / reanálise", "Satellite / réanalyse"),
    "serie_torre": ("Torre de medición", "Met mast", "Torre de medição", "Mât de mesure"),
    "serie_mcp": ("Torre + MCP de largo plazo", "Mast + long-term MCP", "Torre + MCP de longo prazo",
                  "Mât + MCP long terme"),
    "mcp_aplicado": ("MCP aplicado", "MCP applied", "MCP aplicado", "MCP appliqué"),
    "mcp_r2": ("MCP: R²", "MCP: R²", "MCP: R²", "MCP : R²"),
    "mcp_rmse": ("MCP: RMSE", "MCP: RMSE", "MCP: RMSE", "MCP : RMSE"),
    "torre": ("Torre meteorológica", "Met mast", "Torre meteorológica", "Mât météorologique"),
    "disponible": ("Disponible", "Available", "Disponível", "Disponible"),
    "torre_rec": ("Recuperación de datos de la torre", "Mast data recovery", "Recuperação de dados da torre",
                  "Taux de récupération des données du mât"),
    "perfil_txt": ("Modelo de extrapolación vertical: {modelo}. La velocidad se lleva desde la altura de referencia de "
                   "los datos ({href} m) hasta el buje ({h} m) con la cizalladura (α) y la rugosidad (z0) estimadas en "
                   "la Fase 2.",
                   "Vertical extrapolation model: {modelo}. Wind speed is taken from the data reference height "
                   "({href} m) to hub height ({h} m) using the shear (α) and roughness (z0) estimated in Phase 2.",
                   "Modelo de extrapolação vertical: {modelo}. A velocidade é levada da altura de referência dos "
                   "dados ({href} m) até o cubo ({h} m) com o cisalhamento (α) e a rugosidade (z0) estimados na Fase 2.",
                   "Modèle d'extrapolation verticale : {modelo}. La vitesse est ramenée de la hauteur de référence des "
                   "données ({href} m) à la hauteur du moyeu ({h} m) avec le cisaillement (α) et la rugosité (z0) "
                   "estimés en Phase 2."),
    "v10": ("Velocidad media a 10 m", "Mean wind speed at 10 m", "Velocidade média a 10 m", "Vitesse moyenne à 10 m"),
    "v50": ("Velocidad media a 50 m", "Mean wind speed at 50 m", "Velocidade média a 50 m", "Vitesse moyenne à 50 m"),
    "alpha": ("Exponente de cizalladura α del perfil", "Profile shear exponent α", "Expoente de cisalhamento α do perfil",
              "Exposant de cisaillement α du profil"),
    "alpha_med": ("α calculado: mediana (P25–P75, n)", "Calculated α: median (P25–P75, n)",
                  "α calculado: mediana (P25–P75, n)", "α calculé : médiane (P25–P75, n)"),
    "ustar": ("Velocidad de fricción u*", "Friction velocity u*", "Velocidade de atrito u*", "Vitesse de frottement u*"),
    "z0": ("Longitud de rugosidad z0", "Roughness length z0", "Comprimento de rugosidade z0", "Longueur de rugosité z0"),
    "rugosidad": ("Clase de rugosidad", "Roughness class", "Classe de rugosidade", "Classe de rugosité"),
    "ti_amb": ("Intensidad de turbulencia ambiente (TI₀)", "Ambient turbulence intensity (TI₀)",
               "Intensidade de turbulência ambiente (TI₀)", "Intensité de turbulence ambiante (TI₀)"),
    "ti15": ("TI a 15 m/s (indicativa, datos horarios)", "TI at 15 m/s (indicative, hourly data)",
             "TI a 15 m/s (indicativa, dados horários)", "TI à 15 m/s (indicative, données horaires)"),
    "dens_std": ("Densidad estándar de referencia", "Standard reference density", "Densidade padrão de referência",
                 "Densité standard de référence"),
    "sector": ("Sector", "Sector", "Setor", "Secteur"),
    "frecuencia": ("Frecuencia (%)", "Frequency (%)", "Frequência (%)", "Fréquence (%)"),
    "v_media_sector": ("Velocidad media (m/s)", "Mean speed (m/s)", "Velocidade média (m/s)", "Vitesse moyenne (m/s)"),
    "sector_txt": ("Frecuencia y velocidad media por sector de 22,5°, calculadas con la misma serie de la rosa de "
                   "vientos ({serie}).",
                   "Frequency and mean speed per 22.5° sector, computed from the same series as the wind rose ({serie}).",
                   "Frequência e velocidade média por setor de 22,5°, calculadas com a mesma série da rosa dos "
                   "ventos ({serie}).",
                   "Fréquence et vitesse moyenne par secteur de 22,5°, calculées avec la même série que la rose des "
                   "vents ({serie})."),
    "rec_torre_t": ("Recomendación: campaña de medición", "Recommendation: measurement campaign",
                    "Recomendação: campanha de medição", "Recommandation : campagne de mesure"),
    "rec_torre_b": ("El recurso se basa en {fuente}, sin torre de medición en el sitio. Para reducir la incertidumbre "
                    "a niveles aceptados por los financiadores se recomienda medir al menos 12 meses con anemómetros "
                    "calibrados a varias alturas (idealmente hasta la altura del buje) y aplicar MCP de largo plazo "
                    "frente a un reanálisis (ERA5 o MERRA-2).",
                    "The resource is based on {fuente}, without an on-site met mast. To reduce uncertainty to levels "
                    "accepted by lenders, measure for at least 12 months with calibrated anemometers at several "
                    "heights (ideally up to hub height) and apply long-term MCP against a reanalysis (ERA5 or MERRA-2).",
                    "O recurso baseia-se em {fuente}, sem torre de medição no sítio. Para reduzir a incerteza a "
                    "níveis aceitos pelos financiadores, recomenda-se medir pelo menos 12 meses com anemômetros "
                    "calibrados em várias alturas (idealmente até a altura do cubo) e aplicar MCP de longo prazo "
                    "frente a uma reanálise (ERA5 ou MERRA-2).",
                    "La ressource repose sur {fuente}, sans mât de mesure sur site. Pour ramener l'incertitude à un "
                    "niveau accepté par les prêteurs, il est recommandé de mesurer au moins 12 mois avec des "
                    "anémomètres étalonnés à plusieurs hauteurs (idéalement jusqu'à la hauteur du moyeu) et "
                    "d'appliquer une MCP long terme par rapport à une réanalyse (ERA5 ou MERRA-2)."),
    "rec_torre_ok_b": ("El recurso utiliza una torre de medición en el sitio (recuperación de datos {rec}). Conviene "
                       "mantener la campaña hasta completar al menos 12 meses y verificar la correlación de largo plazo.",
                       "The resource uses an on-site met mast (data recovery {rec}). Keep the campaign running until "
                       "at least 12 months are complete and verify the long-term correlation.",
                       "O recurso utiliza uma torre de medição no sítio (recuperação de dados {rec}). Convém manter a "
                       "campanha até completar pelo menos 12 meses e verificar a correlação de longo prazo.",
                       "La ressource utilise un mât de mesure sur site (récupération des données {rec}). Il convient "
                       "de poursuivre la campagne jusqu'à au moins 12 mois et de vérifier la corrélation long terme."),
})

# ── 4. Producción de energía ──
_T.update({
    "energia_intro": ("La producción anual (AEP) se calcula en la Fase 5 con el método {metodo} a {h} m, con la curva "
                      "de potencia de la Fase 1, las estelas en modo «{modo}» y las pérdidas aplicadas en cascada "
                      "(cada pérdida sobre la energía que queda tras la anterior).",
                      "Annual energy production (AEP) is computed in Phase 5 with the {metodo} method at {h} m, using "
                      "the Phase 1 power curve, wakes in “{modo}” mode and losses applied in cascade (each loss on "
                      "the energy remaining after the previous one).",
                      "A produção anual (AEP) é calculada na Fase 5 com o método {metodo} a {h} m, com a curva de "
                      "potência da Fase 1, as esteiras no modo «{modo}» e as perdas aplicadas em cascata (cada perda "
                      "sobre a energia restante após a anterior).",
                      "La production annuelle (AEP) est calculée en Phase 5 avec la méthode {metodo} à {h} m, à partir "
                      "de la courbe de puissance de la Phase 1, des sillages en mode « {modo} » et des pertes "
                      "appliquées en cascade (chaque perte sur l'énergie restant après la précédente)."),
    "concepto": ("Concepto", "Item", "Item", "Poste"),
    "perdida_pct": ("Pérdida (%)", "Loss (%)", "Perda (%)", "Perte (%)"),
    "perdida_mwh": ("Pérdida (MWh/año)", "Loss (MWh/yr)", "Perda (MWh/ano)", "Perte (MWh/an)"),
    "aep_acum": ("AEP restante (MWh/año)", "Remaining AEP (MWh/yr)", "AEP restante (MWh/ano)", "AEP restante (MWh/an)"),
    "c_bruta": ("AEP bruta", "Gross AEP", "AEP bruta", "AEP brute"),
    "c_estela": ("Estelas", "Wakes", "Esteiras", "Sillages"),
    "c_disp_turb": ("Disponibilidad de aerogeneradores", "Turbine availability", "Disponibilidade dos aerogeradores",
                    "Disponibilité des éoliennes"),
    "c_disp_red": ("Disponibilidad de la red", "Grid availability", "Disponibilidade da rede", "Disponibilité du réseau"),
    "c_elec": ("Pérdidas eléctricas", "Electrical losses", "Perdas elétricas", "Pertes électriques"),
    "c_hielo": ("Hielo", "Icing", "Gelo", "Givrage"),
    "c_histeresis": ("Histéresis de alta velocidad", "High-wind hysteresis", "Histerese de alta velocidade",
                     "Hystérésis vent fort"),
    "c_curtailment": ("Restricciones (curtailment)", "Curtailment", "Restrições (curtailment)", "Bridage (curtailment)"),
    "c_otras": ("Otras pérdidas", "Other losses", "Outras perdas", "Autres pertes"),
    "c_neta": ("AEP neta", "Net AEP", "AEP líquida", "AEP nette"),
    "cap_cascada": ("Cascada de pérdidas de la AEP bruta a la neta (MWh/año).",
                    "Loss cascade from gross to net AEP (MWh/yr).",
                    "Cascata de perdas da AEP bruta à líquida (MWh/ano).",
                    "Cascade des pertes de l'AEP brute à l'AEP nette (MWh/an)."),
    "perdida_total": ("Pérdida total (bruta → neta)", "Total loss (gross → net)", "Perda total (bruta → líquida)",
                      "Perte totale (brute → nette)"),
    "metodo": ("Método estadístico", "Statistical method", "Método estatístico", "Méthode statistique"),
    "modo_estela": ("Modo de estelas", "Wake mode", "Modo de esteiras", "Mode de sillage"),
    "modelo_estela": ("Modelo de estela", "Wake model", "Modelo de esteira", "Modèle de sillage"),
    "perdida_estela": ("Pérdida por estelas aplicada", "Applied wake loss", "Perda por esteiras aplicada",
                       "Perte de sillage appliquée"),
    "f4_ponderada": ("Pérdida geométrica de la Fase 4 (ponderada por frecuencia)",
                     "Phase 4 geometric loss (frequency-weighted)",
                     "Perda geométrica da Fase 4 (ponderada pela frequência)",
                     "Perte géométrique de la Phase 4 (pondérée par la fréquence)"),
    "nota_f4_f5": ("La Fase 4 pondera la pérdida geométrica por la frecuencia de cada dirección ({f4}); la Fase 5 la "
                   "aplica ponderada por la energía de cada sector ({f5}), por eso los valores difieren.",
                   "Phase 4 weights the geometric loss by the frequency of each direction ({f4}); Phase 5 applies it "
                   "weighted by the energy of each sector ({f5}), which is why the values differ.",
                   "A Fase 4 pondera a perda geométrica pela frequência de cada direção ({f4}); a Fase 5 aplica-a "
                   "ponderada pela energia de cada setor ({f5}), por isso os valores diferem.",
                   "La Phase 4 pondère la perte géométrique par la fréquence de chaque direction ({f4}) ; la Phase 5 "
                   "l'applique pondérée par l'énergie de chaque secteur ({f5}), d'où la différence entre les valeurs."),
    "aep_bruta_col": ("AEP bruta (MWh/año)", "Gross AEP (MWh/yr)", "AEP bruta (MWh/ano)", "AEP brute (MWh/an)"),
    "aep_neta_col": ("AEP neta (MWh/año)", "Net AEP (MWh/yr)", "AEP líquida (MWh/ano)", "AEP nette (MWh/an)"),
    "sector_no": ("El detalle por sector solo está disponible si la Fase 5 se abrió en esta sesión.",
                  "The per-sector detail is only available if Phase 5 was opened in this session.",
                  "O detalhamento por setor só está disponível se a Fase 5 foi aberta nesta sessão.",
                  "Le détail par secteur n'est disponible que si la Phase 5 a été ouverte dans cette session."),
    "wtg_nota": ("La Fase 5 calcula la AEP del parque completo; aquí se reparte por igual entre los aerogeneradores. "
                 "Un reparto real por aerogenerador requiere el cálculo de estelas turbina a turbina.",
                 "Phase 5 computes the AEP of the whole wind farm; here it is split equally among the turbines. A "
                 "real per-turbine split requires a turbine-by-turbine wake calculation.",
                 "A Fase 5 calcula a AEP do parque inteiro; aqui ela é repartida igualmente entre os aerogeradores. "
                 "Uma repartição real por aerogerador requer o cálculo de esteiras turbina a turbina.",
                 "La Phase 5 calcule l'AEP de l'ensemble du parc ; elle est ici répartie à parts égales entre les "
                 "éoliennes. Une répartition réelle par éolienne nécessite un calcul des sillages éolienne par éolienne."),
    "p_nom_kw": ("P nominal (kW)", "Rated P (kW)", "P nominal (kW)", "P nominale (kW)"),
    "fp_col": ("FP (%)", "CF (%)", "FC (%)", "FC (%)"),
})

# ── 5. Incertidumbre ──
_T.update({
    "mc_intro": ("Monte Carlo de la Fase 5 con {n} muestras (semilla {semilla}). El recurso se modela con la "
                 "incertidumbre de los parámetros de Weibull (σk, σc); la curva de potencia, con una σ directa; y las "
                 "estelas y las pérdidas, con σ relativas a su propio valor. La tabla traduce cada entrada a su efecto "
                 "equivalente sobre la AEP.",
                 "Phase 5 Monte Carlo with {n} samples (seed {semilla}). The resource is modelled with the uncertainty "
                 "of the Weibull parameters (σk, σc); the power curve, with a direct σ; and wakes and losses, with σ "
                 "relative to their own value. The table translates each input into its equivalent effect on the AEP.",
                 "Monte Carlo da Fase 5 com {n} amostras (semente {semilla}). O recurso é modelado com a incerteza dos "
                 "parâmetros de Weibull (σk, σc); a curva de potência, com uma σ direta; e as esteiras e as perdas, "
                 "com σ relativas ao próprio valor. A tabela traduz cada entrada em seu efeito equivalente sobre a AEP.",
                 "Monte Carlo de la Phase 5 avec {n} tirages (graine {semilla}). La ressource est modélisée avec "
                 "l'incertitude des paramètres de Weibull (σk, σc) ; la courbe de puissance, avec un σ direct ; les "
                 "sillages et les pertes, avec des σ relatifs à leur propre valeur. Le tableau traduit chaque entrée "
                 "en son effet équivalent sur l'AEP."),
    "componente": ("Componente", "Component", "Componente", "Composante"),
    "sigma_entrada": ("σ de entrada", "Input σ", "σ de entrada", "σ d'entrée"),
    "efecto_aep": ("Efecto en la AEP (σ)", "Effect on AEP (σ)", "Efeito na AEP (σ)", "Effet sur l'AEP (σ)"),
    "u_recurso": ("Recurso eólico (Weibull)", "Wind resource (Weibull)", "Recurso eólico (Weibull)",
                  "Ressource éolienne (Weibull)"),
    "u_curva": ("Curva de potencia", "Power curve", "Curva de potência", "Courbe de puissance"),
    "u_estela": ("Estelas", "Wakes", "Esteiras", "Sillages"),
    "u_perdidas": ("Pérdidas operativas", "Operational losses", "Perdas operacionais", "Pertes d'exploitation"),
    "u_rss": ("Combinación cuadrática (RSS)", "Root sum of squares (RSS)", "Combinação quadrática (RSS)",
              "Somme quadratique (RSS)"),
    "relativa": ("relativa", "relative", "relativa", "relative"),
    "media_mc": ("Media del Monte Carlo", "Monte Carlo mean", "Média do Monte Carlo", "Moyenne du Monte Carlo"),
    "desv_mc": ("Desviación estándar", "Standard deviation", "Desvio padrão", "Écart type"),
    "cv": ("Coeficiente de variación", "Coefficient of variation", "Coeficiente de variação", "Coefficient de variation"),
    "ratio": ("Relación P90/P50", "P90/P50 ratio", "Relação P90/P50", "Rapport P90/P50"),
    "muestras": ("Muestras", "Samples", "Amostras", "Tirages"),
    "cap_mc": ("Distribución de la AEP neta (aproximación normal con la media y la desviación del Monte Carlo) y "
               "percentiles de excedencia.",
               "Net AEP distribution (normal approximation using the Monte Carlo mean and standard deviation) and "
               "exceedance percentiles.",
               "Distribuição da AEP líquida (aproximação normal com a média e o desvio do Monte Carlo) e percentis "
               "de excedência.",
               "Distribution de l'AEP nette (approximation normale avec la moyenne et l'écart type du Monte Carlo) et "
               "percentiles de dépassement."),
    "interp_t": ("Interpretación", "Interpretation", "Interpretação", "Interprétation"),
    "interp_b": ("El P90 ({p90} MWh/año) queda un {dif} por debajo del P50 ({p50} MWh/año). El coeficiente de "
                 "variación del Monte Carlo ({cv}) es coherente con la combinación cuadrática de los componentes "
                 "({rss}). Reducir la incertidumbre exige mejores mediciones del viento, una curva de potencia "
                 "verificada (IEC 61400-12-1) y modelos de estela validados.",
                 "P90 ({p90} MWh/yr) is {dif} below P50 ({p50} MWh/yr). The Monte Carlo coefficient of variation "
                 "({cv}) is consistent with the root sum of squares of the components ({rss}). Reducing uncertainty "
                 "requires better wind measurements, a verified power curve (IEC 61400-12-1) and validated wake models.",
                 "O P90 ({p90} MWh/ano) fica {dif} abaixo do P50 ({p50} MWh/ano). O coeficiente de variação do Monte "
                 "Carlo ({cv}) é coerente com a combinação quadrática dos componentes ({rss}). Reduzir a incerteza "
                 "exige melhores medições do vento, uma curva de potência verificada (IEC 61400-12-1) e modelos de "
                 "esteira validados.",
                 "Le P90 ({p90} MWh/an) se situe {dif} en dessous du P50 ({p50} MWh/an). Le coefficient de variation "
                 "du Monte Carlo ({cv}) est cohérent avec la somme quadratique des composantes ({rss}). Réduire "
                 "l'incertitude exige de meilleures mesures du vent, une courbe de puissance vérifiée (CEI 61400-12-1) "
                 "et des modèles de sillage validés."),
    "gen_t": ("Monte Carlo no ejecutado", "Monte Carlo not run", "Monte Carlo não executado", "Monte Carlo non exécuté"),
    "gen_b": ("La Fase 5 no tiene un Monte Carlo guardado. Los percentiles siguientes son una estimación gaussiana con σ "
              "genéricas por categoría (σ total {sigma}) y no deben usarse para dimensionar deuda. Ejecute el Monte "
              "Carlo en la Fase 5.",
              "Phase 5 has no saved Monte Carlo. The percentiles below are a Gaussian estimate with generic σ per "
              "category (total σ {sigma}) and must not be used to size debt. Run the Monte Carlo in Phase 5.",
              "A Fase 5 não tem um Monte Carlo salvo. Os percentis a seguir são uma estimativa gaussiana com σ "
              "genéricas por categoria (σ total {sigma}) e não devem ser usados para dimensionar dívida. Execute o "
              "Monte Carlo na Fase 5.",
              "La Phase 5 n'a pas de Monte Carlo enregistré. Les percentiles ci-dessous sont une estimation gaussienne "
              "avec des σ génériques par catégorie (σ total {sigma}) et ne doivent pas servir à dimensionner la dette. "
              "Exécutez le Monte Carlo en Phase 5."),
    "categoria": ("Categoría", "Category", "Categoria", "Catégorie"),
    "g_meas": ("A · Medición y adquisición de datos", "A · Measurement and data acquisition",
               "A · Medição e aquisição de dados", "A · Mesure et acquisition des données"),
    "g_lt": ("B · Largo plazo y variabilidad climática", "B · Long term and climate variability",
             "B · Longo prazo e variabilidade climática", "B · Long terme et variabilité climatique"),
    "g_vert": ("C · Extrapolación vertical", "C · Vertical extrapolation", "C · Extrapolação vertical",
               "C · Extrapolation verticale"),
    "g_flow": ("D · Modelado de flujo y estelas", "D · Flow and wake modelling", "D · Modelagem de escoamento e esteiras",
               "D · Modélisation de l'écoulement et des sillages"),
    "g_plant": ("E · Desempeño de la planta", "E · Plant performance", "E · Desempenho da usina",
                "E · Performance de la centrale"),
    "g_pcv": ("F · Verificación de la curva de potencia", "F · Power curve verification",
              "F · Verificação da curva de potência", "F · Vérification de la courbe de puissance"),
    "sigma_total": "σ total",
})

# ── 6. IEC 61400-1 ──
_T.update({
    "iec_intro": ("Clase declarada del aerogenerador: {clase} / categoría de turbulencia {cat}. Se aplica el mismo "
                  "criterio que la Fase 5: la velocidad media anual a la altura del buje no debe superar la V_ave de "
                  "la clase y la TI a 15 m/s no debe superar la TI de referencia de la categoría.",
                  "Declared turbine class: {clase} / turbulence category {cat}. The same criterion as Phase 5 is "
                  "applied: the annual mean wind speed at hub height must not exceed the class V_ave, and the TI at "
                  "15 m/s must not exceed the category reference TI.",
                  "Classe declarada do aerogerador: {clase} / categoria de turbulência {cat}. Aplica-se o mesmo "
                  "critério da Fase 5: a velocidade média anual à altura do cubo não deve superar a V_ave da classe e "
                  "a TI a 15 m/s não deve superar a TI de referência da categoria.",
                  "Classe déclarée de l'éolienne : {clase} / catégorie de turbulence {cat}. Le critère de la Phase 5 "
                  "est appliqué : la vitesse moyenne annuelle à la hauteur du moyeu ne doit pas dépasser la V_ave de "
                  "la classe et la TI à 15 m/s ne doit pas dépasser la TI de référence de la catégorie."),
    "parametro": ("Parámetro", "Parameter", "Parâmetro", "Paramètre"),
    "sitio": ("Sitio", "Site", "Sítio", "Site"),
    "limite": ("Límite de la clase", "Class limit", "Limite da classe", "Limite de la classe"),
    "resultado": ("Resultado", "Result", "Resultado", "Résultat"),
    "iec_vavg": ("Velocidad media anual a la altura del buje", "Annual mean wind speed at hub height",
                 "Velocidade média anual à altura do cubo", "Vitesse moyenne annuelle à la hauteur du moyeu"),
    "iec_vref": ("Velocidad de referencia extrema V_ref (50 años)", "Extreme reference wind speed V_ref (50 years)",
                 "Velocidade de referência extrema V_ref (50 anos)", "Vitesse de référence extrême V_ref (50 ans)"),
    "iec_ti": ("TI a 15 m/s (indicativa)", "TI at 15 m/s (indicative)", "TI a 15 m/s (indicativa)",
               "TI à 15 m/s (indicative)"),
    "iec_dens": ("Densidad del aire", "Air density", "Densidade do ar", "Densité de l'air"),
    "referencia": ("referencia", "reference", "referência", "référence"),
    "iec_ok": ("El sitio es compatible con la clase declarada según el criterio de la Fase 5. La TI se obtiene de "
               "datos horarios y es indicativa: debe confirmarse con datos de 10 minutos y con el análisis de cargas "
               "del fabricante.",
               "The site is compatible with the declared class according to the Phase 5 criterion. The TI comes from "
               "hourly data and is indicative: it must be confirmed with 10-minute data and the manufacturer's load "
               "analysis.",
               "O sítio é compatível com a classe declarada segundo o critério da Fase 5. A TI é obtida de dados "
               "horários e é indicativa: deve ser confirmada com dados de 10 minutos e com a análise de cargas do "
               "fabricante.",
               "Le site est compatible avec la classe déclarée selon le critère de la Phase 5. La TI provient de "
               "données horaires et est indicative : elle doit être confirmée avec des données 10 minutes et "
               "l'analyse des charges du constructeur."),
    "iec_no": ("El sitio NO es compatible con la clase declarada: {motivos}. Se requiere un aerogenerador de otra clase "
               "(o de clase S) o una evaluación de cargas específica del sitio.",
               "The site is NOT compatible with the declared class: {motivos}. A turbine of another class (or class S) "
               "or a site-specific load assessment is required.",
               "O sítio NÃO é compatível com a classe declarada: {motivos}. É necessário um aerogerador de outra "
               "classe (ou classe S) ou uma avaliação de cargas específica do sítio.",
               "Le site n'est PAS compatible avec la classe déclarée : {motivos}. Une éolienne d'une autre classe (ou "
               "de classe S) ou une évaluation des charges spécifique au site est nécessaire."),
    "iec_no_v": ("la velocidad media supera la de la clase", "the mean wind speed exceeds the class value",
                 "a velocidade média supera a da classe", "la vitesse moyenne dépasse celle de la classe"),
    "iec_no_ti": ("la turbulencia supera la de la categoría", "turbulence exceeds the category value",
                  "a turbulência supera a da categoria", "la turbulence dépasse celle de la catégorie"),
    "iec_nd": ("No se pudo determinar la idoneidad: faltan la velocidad media a la altura del buje o la TI a 15 m/s "
               "(complete la Fase 5).",
               "Suitability could not be determined: the mean wind speed at hub height or the TI at 15 m/s is missing "
               "(complete Phase 5).",
               "Não foi possível determinar a adequação: faltam a velocidade média à altura do cubo ou a TI a 15 m/s "
               "(conclua a Fase 5).",
               "L'adéquation n'a pas pu être déterminée : la vitesse moyenne à la hauteur du moyeu ou la TI à 15 m/s "
               "est manquante (terminez la Phase 5)."),
    "iec_ver_t": ("Veredicto IEC 61400-1", "IEC 61400-1 verdict", "Parecer IEC 61400-1", "Avis CEI 61400-1"),
})

# ── 7. Ambiental ──
_T.update({
    "ruido_max": ("Nivel máximo en receptores", "Maximum level at receptors", "Nível máximo nos receptores",
                  "Niveau maximal aux récepteurs"),
    "lim_dia": ("Límite diurno", "Daytime limit", "Limite diurno", "Limite de jour"),
    "lim_noche": ("Límite nocturno", "Night-time limit", "Limite noturno", "Limite de nuit"),
    "lwa": ("Potencia acústica del aerogenerador (LwA)", "Turbine sound power level (LwA)",
            "Potência sonora do aerogerador (LwA)", "Puissance acoustique de l'éolienne (LwA)"),
    "ruido_txt": ("Resultado del estudio de ruido de la Fase 6 (propagación ISO 9613-2). Límites: {origen}.",
                  "Result of the Phase 6 noise study (ISO 9613-2 propagation). Limits: {origen}.",
                  "Resultado do estudo de ruído da Fase 6 (propagação ISO 9613-2). Limites: {origen}.",
                  "Résultat de l'étude acoustique de la Phase 6 (propagation ISO 9613-2). Limites : {origen}."),
    "lim_origen_f6": ("los definidos en la Fase 6", "those set in Phase 6", "os definidos na Fase 6",
                      "celles définies en Phase 6"),
    "lim_origen_pais": ("valores de referencia de {pais}", "reference values for {pais}", "valores de referência de {pais}",
                        "valeurs de référence pour {pais}"),
    "ruido_no": ("El ruido no se evaluó en la Fase 6. Límites de referencia de {pais}: {dia} dB(A) de día y {noche} "
                 "dB(A) de noche.",
                 "Noise was not assessed in Phase 6. Reference limits for {pais}: {dia} dB(A) daytime and {noche} "
                 "dB(A) night-time.",
                 "O ruído não foi avaliado na Fase 6. Limites de referência de {pais}: {dia} dB(A) de dia e {noche} "
                 "dB(A) à noite.",
                 "Le bruit n'a pas été évalué en Phase 6. Limites de référence pour {pais} : {dia} dB(A) de jour et "
                 "{noche} dB(A) de nuit."),
    "flicker_max": ("Máximo de horas de sombra en receptores", "Maximum shadow hours at receptors",
                    "Máximo de horas de sombra nos receptores", "Maximum d'heures d'ombre aux récepteurs"),
    "flicker_lim": ("Límite de referencia", "Reference limit", "Limite de referência", "Limite de référence"),
    "flicker_txt": ("Resultado del estudio de parpadeo de sombra de la Fase 6.",
                    "Result of the Phase 6 shadow flicker study.",
                    "Resultado do estudo de cintilação de sombra da Fase 6.",
                    "Résultat de l'étude des ombres portées de la Phase 6."),
    "flicker_no": ("El parpadeo de sombra no se evaluó en la Fase 6. Límite de referencia habitual: {lim} h/año por "
                   "receptor.",
                   "Shadow flicker was not assessed in Phase 6. Usual reference limit: {lim} h/yr per receptor.",
                   "A cintilação de sombra não foi avaliada na Fase 6. Limite de referência habitual: {lim} h/ano por "
                   "receptor.",
                   "Les ombres portées n'ont pas été évaluées en Phase 6. Limite de référence habituelle : {lim} h/an "
                   "par récepteur."),
    "otros_1": ("Avifauna y quirópteros (estudio de al menos un ciclo anual).",
                "Birds and bats (study covering at least one annual cycle).",
                "Avifauna e quirópteros (estudo de pelo menos um ciclo anual).",
                "Avifaune et chiroptères (étude sur au moins un cycle annuel)."),
    "otros_2": ("Impacto visual y paisajístico (zona de visibilidad teórica).",
                "Visual and landscape impact (zone of theoretical visibility).",
                "Impacto visual e paisagístico (zona de visibilidade teórica).",
                "Impact visuel et paysager (zone d'influence visuelle théorique)."),
    "otros_3": ("Emisiones de CO₂ evitadas según el factor de emisión de la red del país.",
                "Avoided CO₂ emissions based on the country's grid emission factor.",
                "Emissões de CO₂ evitadas segundo o fator de emissão da rede do país.",
                "Émissions de CO₂ évitées selon le facteur d'émission du réseau du pays."),
    "otros_4": ("Análisis de ciclo de vida (gCO₂/kWh).", "Life-cycle assessment (gCO₂/kWh).",
                "Análise de ciclo de vida (gCO₂/kWh).", "Analyse du cycle de vie (gCO₂/kWh)."),
})

# ── 8. Economía ──
_T.update({
    "eco_intro": ("Modelo económico de la Fase 5: flujo de caja anual antes de impuestos y sin financiación, con la "
                  "energía neta degradada año a año, un precio de venta constante, el OPEX anual y el valor residual "
                  "en el último año.",
                  "Phase 5 economic model: annual pre-tax, unlevered cash flow, with the net energy degraded year by "
                  "year, a constant sale price, the annual OPEX and the residual value in the final year.",
                  "Modelo econômico da Fase 5: fluxo de caixa anual antes de impostos e sem financiamento, com a "
                  "energia líquida degradada ano a ano, preço de venda constante, OPEX anual e valor residual no "
                  "último ano.",
                  "Modèle économique de la Phase 5 : flux de trésorerie annuel avant impôts et sans financement, avec "
                  "l'énergie nette dégradée d'année en année, un prix de vente constant, l'OPEX annuel et la valeur "
                  "résiduelle la dernière année."),
    "moneda_base": ("Moneda base", "Base currency", "Moeda base", "Devise de base"),
    "moneda_vis": ("Moneda de visualización", "Display currency", "Moeda de exibição", "Devise d'affichage"),
    "fx": ("Tasa de cambio usada (COP por USD)", "Exchange rate used (COP per USD)", "Taxa de câmbio usada (COP por USD)",
           "Taux de change utilisé (COP par USD)"),
    "precio": ("Precio de venta de la energía", "Energy sale price", "Preço de venda da energia",
               "Prix de vente de l'énergie"),
    "tasa": ("Tasa de descuento", "Discount rate", "Taxa de desconto", "Taux d'actualisation"),
    "vida": ("Vida útil", "Lifetime", "Vida útil", "Durée de vie"),
    "degr": ("Degradación anual de la energía", "Annual energy degradation", "Degradação anual da energia",
             "Dégradation annuelle de l'énergie"),
    "residual": ("Valor residual", "Residual value", "Valor residual", "Valeur résiduelle"),
    "impuesto": ("Impuesto corporativo del país (informativo, no aplicado)",
                 "Country corporate tax (for information, not applied)",
                 "Imposto corporativo do país (informativo, não aplicado)",
                 "Impôt sur les sociétés du pays (informatif, non appliqué)"),
    "prima_riesgo": ("Prima de riesgo país (informativa)", "Country risk premium (for information)",
                     "Prêmio de risco-país (informativo)", "Prime de risque pays (informative)"),
    "capex_kw": ("CAPEX por kW instalado", "CAPEX per installed kW", "CAPEX por kW instalado", "CAPEX par kW installé"),
    "pct_total": ("% del total", "% of total", "% do total", "% du total"),
    "cap_capex": ("Distribución del CAPEX por concepto.", "CAPEX breakdown by item.", "Distribuição do CAPEX por item.",
                  "Répartition du CAPEX par poste."),
    "opex_mwh": ("OPEX por MWh neto", "OPEX per net MWh", "OPEX por MWh líquido", "OPEX par MWh net"),
    "opex_capex": ("OPEX anual / CAPEX", "Annual OPEX / CAPEX", "OPEX anual / CAPEX", "OPEX annuel / CAPEX"),
    "vp_costos": ("Valor presente de los costos", "Present value of costs", "Valor presente dos custos",
                  "Valeur actuelle des coûts"),
    "ingresos1": ("Ingresos del año 1", "Year-1 revenue", "Receita do ano 1", "Recettes de l'année 1"),
    "margen1": ("Margen operativo del año 1", "Year-1 operating margin", "Margem operacional do ano 1",
                "Marge d'exploitation de l'année 1"),
    "anio": ("Año", "Year", "Ano", "Année"),
    "energia_col": ("Energía (MWh)", "Energy (MWh)", "Energia (MWh)", "Énergie (MWh)"),
    "ingresos": ("Ingresos", "Revenue", "Receitas", "Recettes"),
    "opex_col": "OPEX",
    "inversion": ("Inversión", "Investment", "Investimento", "Investissement"),
    "flujo": ("Flujo neto", "Net cash flow", "Fluxo líquido", "Flux net"),
    "flujo_desc": ("Flujo descontado", "Discounted cash flow", "Fluxo descontado", "Flux actualisé"),
    "acum_desc": ("Acumulado descontado", "Cumulative discounted", "Acumulado descontado", "Cumul actualisé"),
    "flujo_nota": ("Valores en {moneda}. El VPN de este flujo ({npv}) coincide con el de la Fase 5.",
                   "Values in {moneda}. The NPV of this cash flow ({npv}) matches Phase 5.",
                   "Valores em {moneda}. O VPL deste fluxo ({npv}) coincide com o da Fase 5.",
                   "Valeurs en {moneda}. La VAN de ce flux ({npv}) correspond à celle de la Phase 5."),
    "flujo_no": ("Flujo de caja no disponible: faltan el precio de venta o la AEP neta.",
                 "Cash flow not available: the sale price or the net AEP is missing.",
                 "Fluxo de caixa não disponível: faltam o preço de venda ou a AEP líquida.",
                 "Flux de trésorerie non disponible : le prix de vente ou l'AEP nette est manquant."),
    "cap_flujo": ("Flujo de caja anual y acumulado descontado ({moneda}).",
                  "Annual cash flow and cumulative discounted cash flow ({moneda}).",
                  "Fluxo de caixa anual e acumulado descontado ({moneda}).",
                  "Flux de trésorerie annuel et cumul actualisé ({moneda})."),
    "sens_intro": ("Variación del VPN al cambiar cada variable ±{d} % con las demás en el caso base (mismo modelo de "
                   "la Fase 5).",
                   "Change in NPV when each variable is varied by ±{d} % with the others at base case (same model "
                   "as Phase 5).",
                   "Variação do VPL ao alterar cada variável em ±{d} % com as demais no caso base (mesmo modelo da "
                   "Fase 5).",
                   "Variation de la VAN lorsque chaque variable varie de ±{d} % avec les autres au cas de base (même "
                   "modèle que la Phase 5)."),
    "variable": ("Variable", "Variable", "Variável", "Variable"),
    "npv_menos": ("VPN con −{d} %", "NPV at −{d} %", "VPL com −{d} %", "VAN à −{d} %"),
    "npv_base": ("VPN base", "Base NPV", "VPL base", "VAN de base"),
    "npv_mas": ("VPN con +{d} %", "NPV at +{d} %", "VPL com +{d} %", "VAN à +{d} %"),
    "rango": ("Rango", "Range", "Amplitude", "Amplitude"),
    "v_precio": ("Precio de venta", "Sale price", "Preço de venda", "Prix de vente"),
    "v_aep": ("AEP neta", "Net AEP", "AEP líquida", "AEP nette"),
    "v_capex": "CAPEX",
    "v_opex": "OPEX",
    "cap_tornado": ("Sensibilidad del VPN (±{d} %).", "NPV sensitivity (±{d} %).", "Sensibilidade do VPL (±{d} %).",
                    "Sensibilité de la VAN (±{d} %)."),
    "sens_no": ("Sensibilidad no disponible: faltan datos económicos del caso base.",
                "Sensitivity not available: base-case economic data are missing.",
                "Sensibilidade não disponível: faltam dados econômicos do caso base.",
                "Sensibilité non disponible : les données économiques du cas de base sont manquantes."),
    "reg_intro": ("Caracterización indicativa del marco de {pais}; debe validarse con asesoría legal local antes del "
                  "cierre financiero.",
                  "Indicative description of the framework in {pais}; it must be validated with local legal advice "
                  "before financial close.",
                  "Caracterização indicativa do marco de {pais}; deve ser validada com assessoria jurídica local antes "
                  "do fechamento financeiro.",
                  "Description indicative du cadre de {pais} ; à valider avec un conseil juridique local avant le "
                  "bouclage financier."),
    "aspecto": ("Aspecto", "Aspect", "Aspecto", "Aspect"),
    "detalle": ("Detalle", "Detail", "Detalhe", "Détail"),
    "mecanismo": ("Mecanismo de remuneración", "Remuneration mechanism", "Mecanismo de remuneração",
                  "Mécanisme de rémunération"),
    "valor_ref_mec": ("Valor de referencia del mecanismo", "Mechanism reference value", "Valor de referência do mecanismo",
                      "Valeur de référence du mécanisme"),
    "moneda_local": ("Moneda local", "Local currency", "Moeda local", "Devise locale"),
    "fx_aprox": ("Tipo de cambio aproximado", "Approximate exchange rate", "Taxa de câmbio aproximada",
                 "Taux de change approximatif"),
    "limites_ruido": ("Límites de ruido de referencia (día / noche)", "Reference noise limits (day / night)",
                      "Limites de ruído de referência (dia / noite)", "Limites de bruit de référence (jour / nuit)"),
    "legal_t": ("Recomendaciones legales clave", "Key legal recommendations", "Recomendações jurídicas principais",
                "Principales recommandations juridiques"),
    "legal_1": ("Verificar la elegibilidad para los mecanismos de remuneración (subastas, contratos por diferencia, "
                "certificados).",
                "Verify eligibility for remuneration mechanisms (auctions, contracts for difference, certificates).",
                "Verificar a elegibilidade para os mecanismos de remuneração (leilões, contratos por diferença, "
                "certificados).",
                "Vérifier l'éligibilité aux mécanismes de rémunération (appels d'offres, contrats pour différence, "
                "certificats)."),
    "legal_2": ("Confirmar el uso del suelo y las servidumbres con la autoridad competente.",
                "Confirm land use and easements with the competent authority.",
                "Confirmar o uso do solo e as servidões com a autoridade competente.",
                "Confirmer l'usage des sols et les servitudes auprès de l'autorité compétente."),
    "legal_3": ("Revisar los requisitos de consulta previa con comunidades (Convenio 169 de la OIT, si aplica).",
                "Review prior consultation requirements with communities (ILO Convention 169, if applicable).",
                "Revisar os requisitos de consulta prévia às comunidades (Convenção 169 da OIT, se aplicável).",
                "Examiner les exigences de consultation préalable des communautés (Convention 169 de l'OIT, le cas "
                "échéant)."),
    "legal_4": ("Negociar el contrato de venta de energía con indexación a la inflación o al dólar.",
                "Negotiate the power purchase agreement with indexation to inflation or to the US dollar.",
                "Negociar o contrato de venda de energia com indexação à inflação ou ao dólar.",
                "Négocier le contrat d'achat d'électricité avec une indexation sur l'inflation ou sur le dollar."),
    "legal_5": ("Validar el régimen tributario aplicable: exenciones, depreciación acelerada y créditos fiscales.",
                "Validate the applicable tax regime: exemptions, accelerated depreciation and tax credits.",
                "Validar o regime tributário aplicável: isenções, depreciação acelerada e créditos fiscais.",
                "Valider le régime fiscal applicable : exonérations, amortissement accéléré et crédits d'impôt."),
})

# Conceptos del CAPEX/OPEX tal como los devuelve calculos_economicos
CONCEPTOS = {
    "Turbinas": ("Aerogeneradores", "Wind turbines", "Aerogeradores", "Éoliennes"),
    "BOP": ("Obra civil y balance de planta (BOP)", "Balance of plant (BOP)", "Balanço da usina (BOP)",
            "Équipements annexes (BOP)"),
    "Red": ("Conexión a la red", "Grid connection", "Conexão à rede", "Raccordement au réseau"),
    "Desarrollo": ("Desarrollo y permisos", "Development and permits", "Desenvolvimento e licenças",
                   "Développement et permis"),
    "Contingencia": ("Contingencia", "Contingency", "Contingência", "Provision pour aléas"),
    "CAPEX manual total": ("CAPEX total (manual)", "Total CAPEX (manual)", "CAPEX total (manual)", "CAPEX total (manuel)"),
    "OPEX fijo por MW": ("OPEX fijo por MW", "Fixed OPEX per MW", "OPEX fixo por MW", "OPEX fixe par MW"),
    "OPEX variable por energía": ("OPEX variable por energía", "Variable OPEX per energy", "OPEX variável por energia",
                                  "OPEX variable par énergie"),
    "Seguros": ("Seguros", "Insurance", "Seguros", "Assurances"),
    "Terreno": ("Terreno", "Land lease", "Terreno", "Foncier"),
    "Administración": ("Administración", "Administration", "Administração", "Administration"),
    "OPEX anual total": ("OPEX anual (total)", "Annual OPEX (total)", "OPEX anual (total)", "OPEX annuel (total)"),
}


def tr_concepto(nombre: str, lang: str = "es") -> str:
    fila = CONCEPTOS.get(str(nombre))
    return fila[_IDX.get(lang, 0)] if fila else str(nombre)


# Valores que la app guarda en español (opciones de sus menús): en español se muestran tal cual;
# aquí van en inglés, portugués y francés.
VALORES = {
    "Automática desde Fase 4": ("Automatic from Phase 4", "Automática a partir da Fase 4", "Automatique depuis la Phase 4"),
    "Manual": ("Manual", "Manual", "Manuel"),
    "50 m": ("50 m series", "Série a 50 m", "Série à 50 m"),
    "10 m": ("10 m series", "Série a 10 m", "Série à 10 m"),
    "Exponencial": ("Power law (exponential)", "Lei de potência (exponencial)", "Loi de puissance (exponentielle)"),
    "Log A (2 puntos)": ("Logarithmic (2 points)", "Logarítmico (2 pontos)", "Logarithmique (2 points)"),
    "Promedio Log-Exp": ("Log-exponential average", "Média logarítmica-exponencial", "Moyenne log-exponentielle"),
    "Comparar Weibull y Rayleigh": ("Weibull and Rayleigh comparison", "Comparação Weibull e Rayleigh",
                                    "Comparaison Weibull et Rayleigh"),
    "Water / Mar": ("Water / sea", "Água / mar", "Eau / mer"),
    "Snow / Nieve": ("Snow", "Neve", "Neige"),
    "Grass / Césped": ("Grass", "Grama", "Herbe"),
    "Farmland / Cultivo": ("Farmland", "Área agrícola", "Terres agricoles"),
    "Forest / Bosque": ("Forest", "Floresta", "Forêt"),
    "City / Ciudad": ("City", "Cidade", "Ville"),
    "En línea": ("Single row", "Em linha", "En ligne"),
    "En cruz": ("Cross", "Em cruz", "En croix"),
    "Matriz rectangular": ("Rectangular grid", "Matriz retangular", "Grille rectangulaire"),
    "Doble fila": ("Double row", "Fila dupla", "Double rangée"),
    "Tresbolillo": ("Staggered", "Quincôncio", "Quinconce"),
    "Matriz triangular": ("Triangular grid", "Matriz triangular", "Grille triangulaire"),
    "Diagonal": ("Diagonal", "Diagonal", "Diagonale"),
    "Circular": ("Circular", "Circular", "Circulaire"),
    "Arco": ("Arc", "Arco", "Arc"),
    "Aleatorio controlado": ("Controlled random", "Aleatório controlado", "Aléatoire contrôlé"),
}

PAISES = {
    "CO": ("Colombia", "Colombia", "Colômbia", "Colombie"),
    "MX": ("México", "Mexico", "México", "Mexique"),
    "BR": ("Brasil", "Brazil", "Brasil", "Brésil"),
    "CL": ("Chile", "Chile", "Chile", "Chili"),
    "AR": ("Argentina", "Argentina", "Argentina", "Argentine"),
    "PE": ("Perú", "Peru", "Peru", "Pérou"),
    "US": ("Estados Unidos", "United States", "Estados Unidos", "États-Unis"),
    "ES": ("España", "Spain", "Espanha", "Espagne"),
    "DE": ("Alemania", "Germany", "Alemanha", "Allemagne"),
    "UK": ("Reino Unido", "United Kingdom", "Reino Unido", "Royaume-Uni"),
    "IN": ("India", "India", "Índia", "Inde"),
    "ZA": ("Sudáfrica", "South Africa", "África do Sul", "Afrique du Sud"),
    "AU": ("Australia", "Australia", "Austrália", "Australie"),
    "OTRO": ("Otro / personalizado", "Other / custom", "Outro / personalizado", "Autre / personnalisé"),
}


def tr_valor(valor, lang: str = "es") -> str:
    """Opción de un menú de la app en el idioma del informe (desconocida o español: tal cual)."""
    texto = "" if valor is None else str(valor)
    fila = VALORES.get(texto.strip())
    if not fila or lang not in ("en", "pt", "fr"):
        return texto
    return fila[_IDX[lang] - 1]


def nombre_pais(codigo, lang: str = "es", defecto=None) -> str:
    fila = PAISES.get(str(codigo or "").upper())
    if not fila:
        return str(defecto if defecto is not None else (codigo or ""))
    return fila[_IDX.get(lang, 0)]


# ── 8.8 Lista de verificación normativa ──
_T.update({
    "check_intro": ("Estado de este informe frente a las principales normas aplicables a parques eólicos terrestres.",
                    "Status of this report against the main standards applicable to onshore wind farms.",
                    "Situação deste relatório frente às principais normas aplicáveis a parques eólicos terrestres.",
                    "Situation de ce rapport au regard des principales normes applicables aux parcs éoliens terrestres."),
    "norma": ("Norma", "Standard", "Norma", "Norme"),
    "estado": ("Estado en este informe", "Status in this report", "Situação neste relatório", "Situation dans ce rapport"),
    "accion": ("Acción requerida", "Action required", "Ação necessária", "Action requise"),
    "ck_iec1_a": ("Idoneidad del sitio (velocidad y turbulencia frente a la clase)",
                  "Site suitability (wind speed and turbulence vs class)",
                  "Adequação do sítio (velocidade e turbulência frente à classe)",
                  "Adéquation du site (vitesse et turbulence par rapport à la classe)"),
    "ck_iec1_e": ("Evaluado en la sección 6: {res} (TI indicativa)", "Assessed in section 6: {res} (indicative TI)",
                  "Avaliado na seção 6: {res} (TI indicativa)", "Évalué en section 6 : {res} (TI indicative)"),
    "ck_iec1_x": ("Confirmar con datos de 10 minutos y cargas del fabricante",
                  "Confirm with 10-minute data and manufacturer loads",
                  "Confirmar com dados de 10 minutos e cargas do fabricante",
                  "Confirmer avec des données 10 minutes et les charges du constructeur"),
    "ck_pc_a": ("Verificación de la curva de potencia", "Power curve verification", "Verificação da curva de potência",
                "Vérification de la courbe de puissance"),
    "ck_pc_e": ("Curva definida en la Fase 1, sin verificar", "Curve defined in Phase 1, not verified",
                "Curva definida na Fase 1, não verificada", "Courbe définie en Phase 1, non vérifiée"),
    "ck_pc_x": ("Ensayo de curva de potencia tras la puesta en marcha", "Power curve test after commissioning",
                "Ensaio de curva de potência após o comissionamento", "Essai de courbe de puissance après la mise en service"),
    "ck_unc_a": ("Incertidumbre de la producción (P50/P90)", "Energy yield uncertainty (P50/P90)",
                 "Incerteza da produção (P50/P90)", "Incertitude du productible (P50/P90)"),
    "ck_unc_e_mc": ("Monte Carlo de la Fase 5 (sección 5) con categorías simplificadas",
                    "Phase 5 Monte Carlo (section 5) with simplified categories",
                    "Monte Carlo da Fase 5 (seção 5) com categorias simplificadas",
                    "Monte Carlo de la Phase 5 (section 5) avec des catégories simplifiées"),
    "ck_unc_e_gen": ("Estimación genérica, sin Monte Carlo", "Generic estimate, no Monte Carlo",
                     "Estimativa genérica, sem Monte Carlo", "Estimation générique, sans Monte Carlo"),
    "ck_unc_x": ("Presupuesto completo de incertidumbre por un consultor independiente",
                 "Full uncertainty budget by an independent consultant",
                 "Orçamento completo de incerteza por um consultor independente",
                 "Bilan d'incertitude complet par un consultant indépendant"),
    "ck_ruido_a": ("Propagación del ruido en exteriores", "Outdoor noise propagation",
                   "Propagação do ruído em ambiente externo", "Propagation du bruit en extérieur"),
    "ck_eval_f6": ("Evaluado en la Fase 6: {res}", "Assessed in Phase 6: {res}", "Avaliado na Fase 6: {res}",
                   "Évalué en Phase 6 : {res}"),
    "ck_ruido_x": ("Estudio acústico con mediciones del ruido de fondo", "Acoustic study with background noise measurements",
                   "Estudo acústico com medições do ruído de fundo", "Étude acoustique avec mesures du bruit résiduel"),
    "ck_flicker_a": ("Parpadeo de sombra", "Shadow flicker", "Cintilação de sombra", "Ombres portées"),
    "ck_flicker_x": ("Confirmar receptores y medidas de mitigación", "Confirm receptors and mitigation measures",
                     "Confirmar receptores e medidas de mitigação", "Confirmer les récepteurs et les mesures d'atténuation"),
    "ck_cert_a": ("Certificación de proyecto del parque", "Wind farm project certification",
                  "Certificação de projeto do parque", "Certification de projet du parc"),
    "ck_cert_x": ("Certificación por una entidad acreditada", "Certification by an accredited body",
                  "Certificação por uma entidade acreditada", "Certification par un organisme accrédité"),
    "ck_cargas_a": ("Cargas y condiciones del sitio", "Loads and site conditions", "Cargas e condições do sítio",
                    "Charges et conditions du site"),
    "ck_cargas_x": ("Análisis de cargas específico del sitio", "Site-specific load analysis",
                    "Análise de cargas específica do sítio", "Analyse des charges spécifique au site"),
    "ck_iso14001_a": ("Gestión ambiental", "Environmental management", "Gestão ambiental", "Management environnemental"),
    "ck_iso14001_x": ("Plan de gestión ambiental para construcción y operación",
                      "Environmental management plan for construction and operation",
                      "Plano de gestão ambiental para construção e operação",
                      "Plan de management environnemental pour la construction et l'exploitation"),
    "ck_ifc_a": ("Desempeño ambiental y social (financiación internacional)",
                 "Environmental and social performance (international finance)",
                 "Desempenho ambiental e social (financiamento internacional)",
                 "Performance environnementale et sociale (financement international)"),
    "ck_ifc_x": ("Due diligence ambiental y social de tercera parte", "Third-party environmental and social due diligence",
                 "Due diligence ambiental e social de terceira parte", "Due diligence environnementale et sociale par un tiers"),
    "ck_fuera": ("Fuera del alcance de este informe", "Outside the scope of this report", "Fora do escopo deste relatório",
                 "Hors du périmètre de ce rapport"),
})

# ── 9. Registro de riesgos ──
_T.update({
    "riesgos_nota": ("Plantilla de riesgos típicos de un proyecto eólico. La probabilidad y el impacto son orientativos; "
                     "los marcados con * se ajustan con resultados de este proyecto. Deben evaluarse con el equipo del "
                     "proyecto.",
                     "Template of typical wind project risks. Likelihood and impact are indicative; those marked with * "
                     "are adjusted using results of this project. They must be assessed with the project team.",
                     "Modelo de riscos típicos de um projeto eólico. A probabilidade e o impacto são indicativos; os "
                     "marcados com * são ajustados com resultados deste projeto. Devem ser avaliados com a equipe do "
                     "projeto.",
                     "Modèle de risques typiques d'un projet éolien. La probabilité et l'impact sont indicatifs ; ceux "
                     "marqués d'un * sont ajustés à partir des résultats de ce projet. Ils doivent être évalués avec "
                     "l'équipe projet."),
    "r_cat": ("Categoría", "Category", "Categoria", "Catégorie"),
    "r_riesgo": ("Riesgo", "Risk", "Risco", "Risque"),
    "r_prob": ("Probabilidad", "Likelihood", "Probabilidade", "Probabilité"),
    "r_imp": ("Impacto", "Impact", "Impacto", "Impact"),
    "r_nivel": ("Nivel", "Rating", "Nível", "Niveau"),
    "r_mit": ("Mitigación", "Mitigation", "Mitigação", "Atténuation"),
    "baja": ("Baja", "Low", "Baixa", "Faible"),
    "media": ("Media", "Medium", "Média", "Moyenne"),
    "alta": ("Alta", "High", "Alta", "Élevée"),
    "bajo": ("Bajo", "Low", "Baixo", "Faible"),
    "medio": ("Medio", "Medium", "Médio", "Moyen"),
    "alto": ("Alto", "High", "Alto", "Élevé"),
    "critico": ("Crítico", "Critical", "Crítico", "Critique"),
    "cat_tec": ("Técnico", "Technical", "Técnico", "Technique"),
    "cat_op": ("Operativo", "Operational", "Operacional", "Exploitation"),
    "cat_reg": ("Regulatorio", "Regulatory", "Regulatório", "Réglementaire"),
    "cat_fin": ("Financiero", "Financial", "Financeiro", "Financier"),
    "cat_soc": ("Social", "Social", "Social", "Social"),
    "cat_amb": ("Ambiental", "Environmental", "Ambiental", "Environnemental"),
    "cat_red": ("Red", "Grid", "Rede", "Réseau"),
    "cat_con": ("Construcción", "Construction", "Construção", "Construction"),
    "r1": ("Variabilidad interanual del recurso eólico", "Inter-annual variability of the wind resource",
           "Variabilidade interanual do recurso eólico", "Variabilité interannuelle de la ressource éolienne"),
    "m1": ("Torre de medición en el sitio + MCP con ≥ 10 años de datos", "On-site met mast + MCP with ≥ 10 years of data",
           "Torre de medição no sítio + MCP com ≥ 10 anos de dados", "Mât de mesure sur site + MCP avec ≥ 10 ans de données"),
    "r2": ("Pérdidas por estelas distintas a las estimadas", "Wake losses different from those estimated",
           "Perdas por esteiras diferentes das estimadas", "Pertes de sillage différentes des estimations"),
    "m2": ("Contrastar con otro modelo de estela (py_wake, WindFarmer)", "Cross-check with another wake model (py_wake, WindFarmer)",
           "Comparar com outro modelo de esteira (py_wake, WindFarmer)",
           "Comparer avec un autre modèle de sillage (py_wake, WindFarmer)"),
    "r3": ("Desviación de la curva de potencia", "Power curve deviation", "Desvio da curva de potência",
           "Écart de la courbe de puissance"),
    "m3": ("Garantía de curva del fabricante + ensayo IEC 61400-12-1", "Manufacturer power curve warranty + IEC 61400-12-1 test",
           "Garantia de curva do fabricante + ensaio IEC 61400-12-1",
           "Garantie de courbe du constructeur + essai CEI 61400-12-1"),
    "r4": ("Disponibilidad menor a la esperada", "Lower than expected availability", "Disponibilidade menor que a esperada",
           "Disponibilité inférieure aux prévisions"),
    "m4": ("Contrato de O&M con garantía de disponibilidad", "O&M contract with availability guarantee",
           "Contrato de O&M com garantia de disponibilidade", "Contrat d'exploitation-maintenance avec garantie de disponibilité"),
    "r5": ("Pérdidas eléctricas mayores a las estimadas", "Electrical losses higher than estimated",
           "Perdas elétricas maiores que as estimadas", "Pertes électriques supérieures aux estimations"),
    "m5": ("Diseño eléctrico detallado y revisión independiente", "Detailed electrical design and independent review",
           "Projeto elétrico detalhado e revisão independente", "Conception électrique détaillée et revue indépendante"),
    "r6": ("Cambios en el mecanismo de remuneración ({mec})", "Changes to the remuneration mechanism ({mec})",
           "Mudanças no mecanismo de remuneração ({mec})", "Modification du mécanisme de rémunération ({mec})"),
    "m6": ("Contrato bilateral de largo plazo o cobertura de precio", "Long-term bilateral contract or price hedge",
           "Contrato bilateral de longo prazo ou hedge de preço", "Contrat bilatéral de long terme ou couverture de prix"),
    "r7": ("Volatilidad del tipo de cambio {cur}/USD", "{cur}/USD exchange-rate volatility",
           "Volatilidade da taxa de câmbio {cur}/USD", "Volatilité du taux de change {cur}/USD"),
    "m7": ("Cobertura cambiaria o financiación en moneda local", "Currency hedging or local-currency financing",
           "Hedge cambial ou financiamento em moeda local", "Couverture de change ou financement en devise locale"),
    "r8": ("Subida de las tasas de interés (WACC mayor al del caso base)", "Rising interest rates (WACC above base case)",
           "Alta das taxas de juros (WACC acima do caso base)", "Hausse des taux d'intérêt (WACC supérieur au cas de base)"),
    "m8": ("Cierre financiero con tasa fija o coberturas", "Financial close at a fixed rate or with hedges",
           "Fechamento financeiro com taxa fixa ou hedge", "Bouclage financier à taux fixe ou avec couvertures"),
    "r9": ("Consulta con comunidades y permisos locales", "Community consultation and local permits",
           "Consulta às comunidades e licenças locais", "Consultation des communautés et permis locaux"),
    "m9": ("Relacionamiento temprano desde la fase de desarrollo", "Early engagement from the development phase",
           "Relacionamento antecipado desde a fase de desenvolvimento", "Concertation précoce dès la phase de développement"),
    "r10": ("Licencia ambiental y estudio de impacto", "Environmental licence and impact assessment",
            "Licença ambiental e estudo de impacto", "Autorisation environnementale et étude d'impact"),
    "m10": ("Estudios ambientales en paralelo al desarrollo técnico", "Environmental studies in parallel with technical development",
            "Estudos ambientais em paralelo ao desenvolvimento técnico",
            "Études environnementales menées en parallèle du développement technique"),
    "r11": ("Capacidad de conexión a la red", "Grid connection capacity", "Capacidade de conexão à rede",
            "Capacité de raccordement au réseau"),
    "m11": ("Confirmar la capacidad con el operador de la red antes de la decisión de inversión",
            "Confirm capacity with the grid operator before the investment decision",
            "Confirmar a capacidade com o operador da rede antes da decisão de investimento",
            "Confirmer la capacité avec le gestionnaire de réseau avant la décision d'investissement"),
    "r12": ("Sobrecostos o retrasos en la construcción", "Construction cost overruns or delays",
            "Sobrecustos ou atrasos na construção", "Dépassements de coûts ou retards de construction"),
    "m12": ("Contrato EPC llave en mano con penalidades + contingencia ≥ 10 %",
            "Turnkey EPC contract with liquidated damages + contingency ≥ 10 %",
            "Contrato EPC turnkey com multas + contingência ≥ 10 %",
            "Contrat EPC clé en main avec pénalités + provision ≥ 10 %"),
    "r_iec": ("Sitio fuera de la clase IEC declarada*", "Site outside the declared IEC class*",
              "Sítio fora da classe IEC declarada*", "Site hors de la classe CEI déclarée*"),
    "m_iec": ("Elegir un aerogenerador de clase adecuada (o clase S) con análisis de cargas",
              "Choose a turbine of a suitable class (or class S) with a load analysis",
              "Escolher um aerogerador de classe adequada (ou classe S) com análise de cargas",
              "Choisir une éolienne de classe adaptée (ou classe S) avec une analyse des charges"),
    "r_ruido": ("Ruido por encima del límite en receptores*", "Noise above the limit at receptors*",
                "Ruído acima do limite nos receptores*", "Bruit au-dessus de la limite aux récepteurs*"),
    "m_ruido": ("Modos de operación de bajo ruido o reubicación de aerogeneradores", "Low-noise operating modes or turbine relocation",
                "Modos de operação de baixo ruído ou realocação de aerogeradores",
                "Modes de fonctionnement réduits ou déplacement d'éoliennes"),
    "r_flicker": ("Parpadeo de sombra por encima del límite*", "Shadow flicker above the limit*",
                  "Cintilação de sombra acima do limite*", "Ombres portées au-dessus de la limite*"),
    "m_flicker": ("Parada programada en horas críticas o pantallas", "Scheduled shutdown at critical hours or screening",
                  "Parada programada nas horas críticas ou barreiras", "Arrêt programmé aux heures critiques ou écrans"),
    "r_datos": ("Costos o precio posiblemente en una moneda o escala incorrecta*",
                "Costs or price possibly in the wrong currency or scale*",
                "Custos ou preço possivelmente em moeda ou escala incorreta*",
                "Coûts ou prix possiblement dans une devise ou une échelle erronée*"),
    "m_datos": ("Revisar la moneda y los costos de la Fase 5 antes de usar los indicadores",
                "Review the currency and Phase 5 costs before using the indicators",
                "Revisar a moeda e os custos da Fase 5 antes de usar os indicadores",
                "Vérifier la devise et les coûts de la Phase 5 avant d'utiliser les indicateurs"),
})

# ── 10. Conclusiones ──
_T.update({
    "concl_intro": ("El proyecto {nombre} ({pais}) presenta los indicadores técnicos y económicos resumidos en este "
                    "informe. Antes de una decisión de inversión se recomienda:",
                    "The {nombre} project ({pais}) shows the technical and economic indicators summarised in this "
                    "report. Before an investment decision it is recommended to:",
                    "O projeto {nombre} ({pais}) apresenta os indicadores técnicos e econômicos resumidos neste "
                    "relatório. Antes de uma decisão de investimento, recomenda-se:",
                    "Le projet {nombre} ({pais}) présente les indicateurs techniques et économiques résumés dans ce "
                    "rapport. Avant toute décision d'investissement, il est recommandé de :"),
    "rc_validar": ("Validar la AEP P50/P90 con un consultor independiente (WAsP, WindPRO, openWind o WindFarmer).",
                   "Validate the P50/P90 AEP with an independent consultant (WAsP, WindPRO, openWind or WindFarmer).",
                   "Validar a AEP P50/P90 com um consultor independente (WAsP, WindPRO, openWind ou WindFarmer).",
                   "faire valider l'AEP P50/P90 par un consultant indépendant (WAsP, WindPRO, openWind ou WindFarmer) ;"),
    "rc_medicion": ("Instalar una torre de medición en el sitio (≥ 12 meses, varias alturas) y aplicar MCP de largo "
                    "plazo: hoy el recurso depende solo de {fuente}.",
                    "Install an on-site met mast (≥ 12 months, several heights) and apply long-term MCP: the resource "
                    "currently relies only on {fuente}.",
                    "Instalar uma torre de medição no sítio (≥ 12 meses, várias alturas) e aplicar MCP de longo prazo: "
                    "hoje o recurso depende apenas de {fuente}.",
                    "installer un mât de mesure sur site (≥ 12 mois, plusieurs hauteurs) et appliquer une MCP long "
                    "terme : la ressource repose aujourd'hui uniquement sur {fuente} ;"),
    "rc_torre_ok": ("Completar al menos 12 meses de medición en la torre y verificar la correlación de largo plazo.",
                    "Complete at least 12 months of mast measurements and verify the long-term correlation.",
                    "Completar pelo menos 12 meses de medição na torre e verificar a correlação de longo prazo.",
                    "compléter au moins 12 mois de mesures au mât et vérifier la corrélation long terme ;"),
    "rc_iec_no": ("Seleccionar un aerogenerador compatible con el sitio: la clase declarada {clase}/{cat} no cumple el "
                  "criterio de la sección 6.",
                  "Select a turbine compatible with the site: the declared class {clase}/{cat} does not meet the "
                  "section 6 criterion.",
                  "Selecionar um aerogerador compatível com o sítio: a classe declarada {clase}/{cat} não atende ao "
                  "critério da seção 6.",
                  "choisir une éolienne compatible avec le site : la classe déclarée {clase}/{cat} ne satisfait pas le "
                  "critère de la section 6 ;"),
    "rc_ti": ("Confirmar la turbulencia con datos de 10 minutos: la TI de este informe es indicativa.",
              "Confirm turbulence with 10-minute data: the TI in this report is indicative.",
              "Confirmar a turbulência com dados de 10 minutos: a TI deste relatório é indicativa.",
              "confirmer la turbulence avec des données 10 minutes : la TI de ce rapport est indicative ;"),
    "rc_ruido": ("Mitigar el ruido: el nivel máximo ({db} dB(A)) supera el límite nocturno ({lim} dB(A)).",
                 "Mitigate noise: the maximum level ({db} dB(A)) exceeds the night-time limit ({lim} dB(A)).",
                 "Mitigar o ruído: o nível máximo ({db} dB(A)) supera o limite noturno ({lim} dB(A)).",
                 "atténuer le bruit : le niveau maximal ({db} dB(A)) dépasse la limite de nuit ({lim} dB(A)) ;"),
    "rc_flicker": ("Mitigar el parpadeo de sombra: {h} h/año superan el límite de {lim} h/año.",
                   "Mitigate shadow flicker: {h} h/yr exceed the {lim} h/yr limit.",
                   "Mitigar a cintilação de sombra: {h} h/ano superam o limite de {lim} h/ano.",
                   "atténuer les ombres portées : {h} h/an dépassent la limite de {lim} h/an ;"),
    "rc_amb_no": ("Realizar los estudios de ruido (ISO 9613-2) y de parpadeo de sombra antes de solicitar los permisos.",
                  "Carry out the noise (ISO 9613-2) and shadow flicker studies before applying for permits.",
                  "Realizar os estudos de ruído (ISO 9613-2) e de cintilação de sombra antes de solicitar as licenças.",
                  "réaliser les études de bruit (ISO 9613-2) et d'ombres portées avant de demander les autorisations ;"),
    "rc_datos": ("Revisar la moneda y los valores económicos de la Fase 5: los avisos de coherencia indican que los "
                 "indicadores financieros no son representativos.",
                 "Review the currency and the Phase 5 economic values: the consistency warnings indicate that the "
                 "financial indicators are not representative.",
                 "Revisar a moeda e os valores econômicos da Fase 5: os avisos de coerência indicam que os indicadores "
                 "financeiros não são representativos.",
                 "vérifier la devise et les valeurs économiques de la Phase 5 : les avertissements de cohérence "
                 "indiquent que les indicateurs financiers ne sont pas représentatifs ;"),
    "rc_iterar": ("Iterar el precio de venta, la disposición, el aerogenerador o los costos: la TIR ({irr}) no supera el "
                  "WACC típico del país ({wacc}).",
                  "Iterate the sale price, layout, turbine or costs: the IRR ({irr}) does not exceed the typical "
                  "country WACC ({wacc}).",
                  "Iterar o preço de venda, o layout, o aerogerador ou os custos: a TIR ({irr}) não supera o WACC "
                  "típico do país ({wacc}).",
                  "itérer le prix de vente, l'implantation, l'éolienne ou les coûts : le TRI ({irr}) ne dépasse pas le "
                  "WACC typique du pays ({wacc}) ;"),
    "rc_contingencia": ("Mantener una contingencia de al menos el 10 % del CAPEX para sobrecostos de construcción.",
                        "Keep a contingency of at least 10 % of CAPEX for construction cost overruns.",
                        "Manter uma contingência de pelo menos 10 % do CAPEX para sobrecustos de construção.",
                        "conserver une provision d'au moins 10 % du CAPEX pour les dépassements de coûts de construction ;"),
    "rc_red": ("Confirmar la capacidad de conexión con el operador de la red antes de comprometer el CAPEX.",
               "Confirm connection capacity with the grid operator before committing CAPEX.",
               "Confirmar a capacidade de conexão com o operador da rede antes de comprometer o CAPEX.",
               "confirmer la capacité de raccordement avec le gestionnaire de réseau avant d'engager le CAPEX ;"),
    "rc_suelo": ("Cerrar los acuerdos de uso del suelo y la consulta con las comunidades antes de la decisión final de "
                 "inversión.",
                 "Close land-use agreements and community consultation before the final investment decision.",
                 "Fechar os acordos de uso do solo e a consulta às comunidades antes da decisão final de investimento.",
                 "conclure les accords fonciers et la consultation des communautés avant la décision finale "
                 "d'investissement."),
})

# ── 11. Apéndices ──
_T.update({
    "ma_datos": ("Datos de viento: {fuente}, periodo {inicio} → {fin}, altura de referencia {href} m; serie utilizada: {serie}.",
                 "Wind data: {fuente}, period {inicio} → {fin}, reference height {href} m; series used: {serie}.",
                 "Dados de vento: {fuente}, período {inicio} → {fin}, altura de referência {href} m; série utilizada: {serie}.",
                 "Données de vent : {fuente}, période {inicio} → {fin}, hauteur de référence {href} m ; série utilisée : {serie}."),
    "ma_perfil": ("Extrapolación vertical: {modelo} hasta {h} m (α = {alpha}; z0 = {z0} m).",
                  "Vertical extrapolation: {modelo} up to {h} m (α = {alpha}; z0 = {z0} m).",
                  "Extrapolação vertical: {modelo} até {h} m (α = {alpha}; z0 = {z0} m).",
                  "Extrapolation verticale : {modelo} jusqu'à {h} m (α = {alpha} ; z0 = {z0} m)."),
    "ma_energia": ("Producción: método {metodo} con la curva de potencia de la Fase 1; estelas en modo «{modo}» "
                   "(modelo {modelo}); pérdidas aplicadas en cascada.",
                   "Production: {metodo} method with the Phase 1 power curve; wakes in “{modo}” mode ({modelo} model); "
                   "losses applied in cascade.",
                   "Produção: método {metodo} com a curva de potência da Fase 1; esteiras no modo «{modo}» (modelo "
                   "{modelo}); perdas aplicadas em cascata.",
                   "Production : méthode {metodo} avec la courbe de puissance de la Phase 1 ; sillages en mode « {modo} » "
                   "(modèle {modelo}) ; pertes appliquées en cascade."),
    "ma_incert": ("Incertidumbre: Monte Carlo de la Fase 5 ({n} muestras) sobre recurso, curva de potencia, estelas y pérdidas.",
                  "Uncertainty: Phase 5 Monte Carlo ({n} samples) on resource, power curve, wakes and losses.",
                  "Incerteza: Monte Carlo da Fase 5 ({n} amostras) sobre recurso, curva de potência, esteiras e perdas.",
                  "Incertitude : Monte Carlo de la Phase 5 ({n} tirages) sur la ressource, la courbe de puissance, les "
                  "sillages et les pertes."),
    "ma_incert_gen": ("Incertidumbre: estimación gaussiana con σ genéricas por categoría (sin Monte Carlo).",
                      "Uncertainty: Gaussian estimate with generic σ per category (no Monte Carlo).",
                      "Incerteza: estimativa gaussiana com σ genéricas por categoria (sem Monte Carlo).",
                      "Incertitude : estimation gaussienne avec des σ génériques par catégorie (sans Monte Carlo)."),
    "ma_iec": ("Idoneidad IEC 61400-1: velocidad media anual a la altura del buje y TI a 15 m/s frente a la clase declarada.",
               "IEC 61400-1 suitability: annual mean wind speed at hub height and TI at 15 m/s against the declared class.",
               "Adequação IEC 61400-1: velocidade média anual à altura do cubo e TI a 15 m/s frente à classe declarada.",
               "Adéquation CEI 61400-1 : vitesse moyenne annuelle à la hauteur du moyeu et TI à 15 m/s par rapport à "
               "la classe déclarée."),
    "ma_eco": ("Economía: flujo de caja anual de la Fase 5 (antes de impuestos y sin financiación), VPN, TIR, LCOE y "
               "sensibilidad de ±{d} %.",
               "Economics: Phase 5 annual cash flow (pre-tax and unlevered), NPV, IRR, LCOE and ±{d} % sensitivity.",
               "Economia: fluxo de caixa anual da Fase 5 (antes de impostos e sem financiamento), VPL, TIR, LCOE e "
               "sensibilidade de ±{d} %.",
               "Économie : flux de trésorerie annuel de la Phase 5 (avant impôts et sans financement), VAN, TRI, LCOE "
               "et sensibilité de ±{d} %."),
    "valid_txt": ("Los resultados provienen de modelos analíticos implementados en SMA 2.0 (perfil vertical, distribución "
                  "de Weibull y modelos de estela de ingeniería). Este informe no incluye una validación de esos modelos "
                  "frente a mediciones de parques en operación; se recomienda contrastar la AEP con software comercial "
                  "(WAsP, WindPRO, openWind) o con py_wake antes de usarla para la financiación.",
                  "The results come from analytical models implemented in SMA 2.0 (vertical profile, Weibull "
                  "distribution and engineering wake models). This report does not include a validation of those "
                  "models against measurements from operating wind farms; the AEP should be cross-checked with "
                  "commercial software (WAsP, WindPRO, openWind) or py_wake before it is used for financing.",
                  "Os resultados provêm de modelos analíticos implementados no SMA 2.0 (perfil vertical, distribuição "
                  "de Weibull e modelos de esteira de engenharia). Este relatório não inclui uma validação desses "
                  "modelos frente a medições de parques em operação; recomenda-se comparar a AEP com software comercial "
                  "(WAsP, WindPRO, openWind) ou com o py_wake antes de usá-la para o financiamento.",
                  "Les résultats proviennent de modèles analytiques implémentés dans SMA 2.0 (profil vertical, "
                  "distribution de Weibull et modèles de sillage d'ingénierie). Ce rapport ne comprend pas de "
                  "validation de ces modèles par rapport à des mesures de parcs en exploitation ; il est recommandé de "
                  "comparer l'AEP avec un logiciel commercial (WAsP, WindPRO, openWind) ou avec py_wake avant de "
                  "l'utiliser pour le financement."),
    "gl_1": ("AEP: producción anual de energía.", "AEP: annual energy production.", "AEP: produção anual de energia.",
             "AEP : production annuelle d'énergie."),
    "gl_2": ("P50/P75/P90/P99: producción anual superada con una probabilidad del 50/75/90/99 %.",
             "P50/P75/P90/P99: annual production exceeded with a probability of 50/75/90/99 %.",
             "P50/P75/P90/P99: produção anual superada com probabilidade de 50/75/90/99 %.",
             "P50/P75/P90/P99 : production annuelle dépassée avec une probabilité de 50/75/90/99 %."),
    "gl_3": ("TI: intensidad de turbulencia.", "TI: turbulence intensity.", "TI: intensidade de turbulência.",
             "TI : intensité de turbulence."),
    "gl_4": ("MCP: medir-correlacionar-predecir (extensión de datos de corto plazo al largo plazo).",
             "MCP: measure-correlate-predict (extending short-term data to the long term).",
             "MCP: medir-correlacionar-prever (extensão de dados de curto prazo para o longo prazo).",
             "MCP : mesure-corrélation-prédiction (extension de données court terme au long terme)."),
    "gl_5": ("Ct: coeficiente de empuje del rotor.", "Ct: rotor thrust coefficient.", "Ct: coeficiente de empuxo do rotor.",
             "Ct : coefficient de poussée du rotor."),
    "gl_6": ("LCOE: costo nivelado de la energía.", "LCOE: levelised cost of energy.", "LCOE: custo nivelado da energia.",
             "LCOE : coût actualisé de l'énergie."),
    "gl_7": ("VPN / TIR: valor presente neto / tasa interna de retorno.", "NPV / IRR: net present value / internal rate of return.",
             "VPL / TIR: valor presente líquido / taxa interna de retorno.",
             "VAN / TRI : valeur actuelle nette / taux de rentabilité interne."),
    "gl_8": ("WACC: costo promedio ponderado del capital.", "WACC: weighted average cost of capital.",
             "WACC: custo médio ponderado de capital.", "WACC : coût moyen pondéré du capital."),
    "gl_9": ("EYA: evaluación de la producción energética.", "EYA: energy yield assessment.",
             "EYA: avaliação da produção energética.", "EYA : évaluation du productible."),
    "gl_10": ("EPC: ingeniería, suministro y construcción.", "EPC: engineering, procurement and construction.",
              "EPC: engenharia, suprimento e construção.", "EPC : ingénierie, approvisionnement et construction."),
    "gl_11": ("FID: decisión final de inversión.", "FID: final investment decision.", "FID: decisão final de investimento.",
              "FID : décision finale d'investissement."),
    "gl_12": ("O&M: operación y mantenimiento.", "O&M: operation and maintenance.", "O&M: operação e manutenção.",
              "O&M : exploitation et maintenance."),
    "refs_intro": ("Referencias en formato APA 7 (se citan en su idioma original).",
                   "References in APA 7 format (cited in their original language).",
                   "Referências no formato APA 7 (citadas no idioma original).",
                   "Références au format APA 7 (citées dans leur langue d'origine)."),
    "limit_txt": ("Este informe se genera automáticamente con los datos configurados en SMA 2.0 y los conjuntos de datos "
                  "disponibles ({fuente}). No incluye: (i) certificación IEC 61400-22 por una entidad acreditada; "
                  "(ii) validación de la AEP por una tercera parte; (iii) due diligence técnica para la financiación "
                  "del proyecto; (iv) modelado CFD del sitio; (v) caracterización de eventos extremos (V_ref, ráfagas); "
                  "(vi) los estudios de impacto ambiental exigidos por la regulación local; (vii) la negociación del "
                  "contrato de venta de energía ni las garantías del fabricante.",
                  "This report is generated automatically from the data configured in SMA 2.0 and the available "
                  "datasets ({fuente}). It does not include: (i) IEC 61400-22 certification by an accredited body; "
                  "(ii) third-party validation of the AEP; (iii) technical due diligence for project finance; "
                  "(iv) CFD modelling of the site; (v) characterisation of extreme events (V_ref, gusts); (vi) the "
                  "environmental impact studies required by local regulation; (vii) negotiation of the power purchase "
                  "agreement or manufacturer warranties.",
                  "Este relatório é gerado automaticamente com os dados configurados no SMA 2.0 e os conjuntos de "
                  "dados disponíveis ({fuente}). Não inclui: (i) certificação IEC 61400-22 por entidade acreditada; "
                  "(ii) validação da AEP por terceira parte; (iii) due diligence técnica para o financiamento do "
                  "projeto; (iv) modelagem CFD do sítio; (v) caracterização de eventos extremos (V_ref, rajadas); "
                  "(vi) os estudos de impacto ambiental exigidos pela regulação local; (vii) a negociação do contrato "
                  "de venda de energia nem as garantias do fabricante.",
                  "Ce rapport est généré automatiquement à partir des données configurées dans SMA 2.0 et des jeux de "
                  "données disponibles ({fuente}). Il ne comprend pas : (i) la certification CEI 61400-22 par un "
                  "organisme accrédité ; (ii) la validation de l'AEP par un tiers ; (iii) la due diligence technique "
                  "pour le financement du projet ; (iv) la modélisation CFD du site ; (v) la caractérisation des "
                  "événements extrêmes (V_ref, rafales) ; (vi) les études d'impact environnemental exigées par la "
                  "réglementation locale ; (vii) la négociation du contrat d'achat d'électricité ni les garanties du "
                  "constructeur."),
})

# ── Etiquetas de las gráficas ──
_T.update({
    "ax_v": ("Velocidad del viento (m/s)", "Wind speed (m/s)", "Velocidade do vento (m/s)", "Vitesse du vent (m/s)"),
    "ax_p_kw": ("Potencia (kW)", "Power (kW)", "Potência (kW)", "Puissance (kW)"),
    "ax_densidad_prob": ("Densidad de probabilidad", "Probability density", "Densidade de probabilidade",
                         "Densité de probabilité"),
    "ax_aep": ("AEP (MWh/año)", "AEP (MWh/yr)", "AEP (MWh/ano)", "AEP (MWh/an)"),
    "lg_media": ("Media = {v} m/s", "Mean = {v} m/s", "Média = {v} m/s", "Moyenne = {v} m/s"),
    "lg_pnom": ("P nominal = {p} kW", "Rated P = {p} kW", "P nominal = {p} kW", "P nominale = {p} kW"),
    "ax_flujo": ("Flujo ({moneda})", "Cash flow ({moneda})", "Fluxo ({moneda})", "Flux ({moneda})"),
    "ax_delta_npv": ("Variación del VPN ({moneda})", "Change in NPV ({moneda})", "Variação do VPL ({moneda})",
                     "Variation de la VAN ({moneda})"),
})

# ── Monte Carlo desactualizado ──
_T.update({
    "mcold_t": ("Monte Carlo desactualizado", "Outdated Monte Carlo", "Monte Carlo desatualizado", "Monte Carlo obsolète"),
    "h_mc_old": ("Incertidumbre: el Monte Carlo guardado es de una configuración anterior; P90 ≈ {p90} MWh/año con una "
                 "σ genérica de {cv}.",
                 "Uncertainty: the saved Monte Carlo is from a previous configuration; P90 ≈ {p90} MWh/yr with a generic "
                 "σ of {cv}.",
                 "Incerteza: o Monte Carlo salvo é de uma configuração anterior; P90 ≈ {p90} MWh/ano com uma σ genérica "
                 "de {cv}.",
                 "Incertitude : le Monte Carlo enregistré provient d'une configuration antérieure ; P90 ≈ {p90} MWh/an "
                 "avec un σ générique de {cv}."),
    "ck_unc_e_old": ("Monte Carlo desactualizado: estimación genérica", "Outdated Monte Carlo: generic estimate",
                     "Monte Carlo desatualizado: estimativa genérica", "Monte Carlo obsolète : estimation générique"),
})

# ── Presentación formal: rótulos de tabla, tarjetas, conclusión, gráficas y diagrama ──
_T.update({
    "tb_portada": ("Datos del documento", "Document data", "Dados do documento", "Données du document"),
    "tb_control": ("Historial de revisiones", "Revision history", "Histórico de revisões", "Historique des révisions"),
    "tb_kpis": ("Indicadores principales del proyecto", "Main project indicators", "Principais indicadores do projeto",
                "Principaux indicateurs du projet"),
    "tb_sitio": ("Localización y condiciones del sitio", "Site location and conditions",
                 "Localização e condições do sítio", "Localisation et conditions du site"),
    "tb_turbina": ("Características del aerogenerador y del parque", "Wind turbine and wind farm characteristics",
                   "Características do aerogerador e do parque", "Caractéristiques de l'éolienne et du parc"),
    "tb_layout": ("Coordenadas de los aerogeneradores", "Wind turbine coordinates", "Coordenadas dos aerogeradores",
                  "Coordonnées des éoliennes"),
    "tb_fuente": ("Fuente y periodo de los datos de viento", "Wind data source and period",
                  "Fonte e período dos dados de vento", "Source et période des données de vent"),
    "tb_perfil": ("Perfil vertical del viento", "Vertical wind profile", "Perfil vertical do vento", "Profil vertical du vent"),
    "tb_ti": ("Turbulencia y densidad del aire", "Turbulence and air density", "Turbulência e densidade do ar",
              "Turbulence et densité de l'air"),
    "tb_sectores": ("Frecuencia y velocidad media por sector", "Frequency and mean speed by sector",
                    "Frequência e velocidade média por setor", "Fréquence et vitesse moyenne par secteur"),
    "tb_cascada": ("Cascada de pérdidas (Fase 5)", "Loss cascade (Phase 5)", "Cascata de perdas (Fase 5)",
                   "Cascade des pertes (Phase 5)"),
    "tb_energia": ("Resumen energético", "Energy summary", "Resumo energético", "Bilan énergétique"),
    "tb_sector_e": ("Energía por sector de dirección", "Energy by direction sector", "Energia por setor de direção",
                    "Énergie par secteur de direction"),
    "tb_wtg": ("Producción estimada por aerogenerador", "Estimated production per turbine",
               "Produção estimada por aerogerador", "Production estimée par éolienne"),
    "tb_unc": ("Componentes de la incertidumbre de la AEP", "AEP uncertainty components", "Componentes da incerteza da AEP",
               "Composantes de l'incertitude de l'AEP"),
    "tb_mc": ("Probabilidades de excedencia de la AEP neta", "Net AEP exceedance probabilities",
              "Probabilidades de excedência da AEP líquida", "Probabilités de dépassement de l'AEP nette"),
    "tb_iec": ("Idoneidad del sitio frente a la clase declarada", "Site suitability against the declared class",
               "Adequação do sítio frente à classe declarada", "Adéquation du site par rapport à la classe déclarée"),
    "tb_ruido": ("Ruido en los receptores", "Noise at receptors", "Ruído nos receptores", "Bruit aux récepteurs"),
    "tb_flicker": ("Parpadeo de sombra en los receptores", "Shadow flicker at receptors", "Cintilação de sombra nos receptores",
                   "Ombres portées aux récepteurs"),
    "tb_supuestos": ("Supuestos económicos", "Economic assumptions", "Premissas econômicas", "Hypothèses économiques"),
    "tb_capex": ("Desglose de la inversión (CAPEX)", "Investment breakdown (CAPEX)", "Detalhamento do investimento (CAPEX)",
                 "Ventilation de l'investissement (CAPEX)"),
    "tb_opex": ("Desglose de los costos de operación (OPEX)", "Operating cost breakdown (OPEX)",
                "Detalhamento dos custos de operação (OPEX)", "Ventilation des coûts d'exploitation (OPEX)"),
    "tb_fin": ("Indicadores financieros del caso base", "Base-case financial indicators", "Indicadores financeiros do caso base",
               "Indicateurs financiers du cas de base"),
    "tb_flujo": ("Flujo de caja anual ({moneda})", "Annual cash flow ({moneda})", "Fluxo de caixa anual ({moneda})",
                 "Flux de trésorerie annuel ({moneda})"),
    "tb_sens": ("Sensibilidad del VPN", "NPV sensitivity", "Sensibilidade do VPL", "Sensibilité de la VAN"),
    "tb_reg": ("Marco regulatorio de referencia", "Reference regulatory framework", "Marco regulatório de referência",
               "Cadre réglementaire de référence"),
    "tb_normas": ("Estado frente a las normas aplicables", "Status against applicable standards",
                  "Situação frente às normas aplicáveis", "Situation au regard des normes applicables"),
    "tb_riesgos": ("Registro de riesgos del proyecto", "Project risk register", "Registro de riscos do projeto",
                   "Registre des risques du projet"),
    "kc_v": ("Viento medio a {h} m", "Mean wind at {h} m", "Vento médio a {h} m", "Vent moyen à {h} m"),
    "concl_pre_t": ("Conclusión preliminar", "Preliminary conclusion", "Conclusão preliminar", "Conclusion préliminaire"),
    "concl_pre_b": ("El parque de {n} aerogeneradores de {kw} kW ({mw} MW) en {pais} produciría {aep} MWh/año netos, con "
                    "un factor de planta de {fp} y un P90 de {p90} MWh/año. Con un precio de venta de {precio}, el caso "
                    "base da un VPN de {npv} y una TIR de {irr}.",
                    "The {n}-turbine wind farm of {kw} kW ({mw} MW) in {pais} would produce {aep} MWh/yr net, with a "
                    "capacity factor of {fp} and a P90 of {p90} MWh/yr. With a sale price of {precio}, the base case "
                    "gives an NPV of {npv} and an IRR of {irr}.",
                    "O parque de {n} aerogeradores de {kw} kW ({mw} MW) em {pais} produziria {aep} MWh/ano líquidos, com "
                    "fator de capacidade de {fp} e P90 de {p90} MWh/ano. Com preço de venda de {precio}, o caso base "
                    "resulta em VPL de {npv} e TIR de {irr}.",
                    "Le parc de {n} éoliennes de {kw} kW ({mw} MW) en {pais} produirait {aep} MWh/an nets, avec un "
                    "facteur de charge de {fp} et un P90 de {p90} MWh/an. Avec un prix de vente de {precio}, le cas de "
                    "base donne une VAN de {npv} et un TRI de {irr}."),
    "confidencial": ("Confidencial", "Confidential", "Confidencial", "Confidentiel"),
    "estado_doc": ("Estado", "Status", "Situação", "Statut"),
    "borrador": ("Borrador para revisión", "Draft for review", "Rascunho para revisão", "Projet pour relecture"),
    "m_arranque": ("Arranque", "Cut-in", "Partida", "Démarrage"),
    "m_nominal": ("Nominal", "Rated", "Nominal", "Nominale"),
    "m_parada": ("Parada", "Cut-out", "Corte", "Coupure"),
    "lg_potencia": ("Potencia", "Power", "Potência", "Puissance"),
    "ax_cp": ("Coeficiente de potencia Cp", "Power coefficient Cp", "Coeficiente de potência Cp", "Coefficient de puissance Cp"),
    "ax_frec_rel": ("Frecuencia relativa", "Relative frequency", "Frequência relativa", "Fréquence relative"),
    "lg_recuperacion": ("Recuperación ≈ año {a}", "Payback ≈ year {a}", "Retorno ≈ ano {a}", "Récupération ≈ année {a}"),
    "lg_area_p90": "P(AEP ≥ P90) = 90 %",
    "cap_rosa2": ("Rosa de vientos por clases de velocidad ({serie}).", "Wind rose by speed class ({serie}).",
                  "Rosa dos ventos por classes de velocidade ({serie}).", "Rose des vents par classes de vitesse ({serie})."),
    "cap_curva2": ("Curva de potencia y coeficiente de potencia (Cp) del aerogenerador.",
                   "Wind turbine power curve and power coefficient (Cp).",
                   "Curva de potência e coeficiente de potência (Cp) do aerogerador.",
                   "Courbe de puissance et coefficient de puissance (Cp) de l'éolienne."),
    "cap_diagrama": ("Metodología del estudio: de los datos de viento a la economía del proyecto.",
                     "Study methodology: from wind data to project economics.",
                     "Metodologia do estudo: dos dados de vento à economia do projeto.",
                     "Méthodologie de l'étude : des données de vent à l'économie du projet."),
    "dg_datos": ("Datos de viento", "Wind data", "Dados de vento", "Données de vent"),
    "dg_perfil": ("Perfil vertical", "Vertical profile", "Perfil vertical", "Profil vertical"),
    "dg_dist": ("Distribución", "Distribution", "Distribuição", "Distribution"),
    "dg_curva": ("Curva de potencia", "Power curve", "Curva de potência", "Courbe de puissance"),
    "dg_estelas": ("Estelas", "Wakes", "Esteiras", "Sillages"),
    "dg_perdidas": ("Pérdidas", "Losses", "Perdas", "Pertes"),
    "dg_aep": ("AEP neta", "Net AEP", "AEP líquida", "AEP nette"),
    "dg_incert": ("Incertidumbre", "Uncertainty", "Incerteza", "Incertitude"),
    "dg_eco": ("Economía", "Economics", "Economia", "Économie"),
    "dg_sectores": ("{metodo} · 16 sectores", "{metodo} · 16 sectors", "{metodo} · 16 setores", "{metodo} · 16 secteurs"),
    "dg_cascada": ("{pct} en cascada", "{pct} in cascade", "{pct} em cascata", "{pct} en cascade"),
    "dg_mc": ("Monte Carlo\n{n} muestras", "Monte Carlo\n{n} samples", "Monte Carlo\n{n} amostras", "Monte Carlo\n{n} tirages"),
    "dg_mc_gen": ("Estimación genérica", "Generic estimate", "Estimativa genérica", "Estimation générique"),
})

# ── FIN DE TEXTOS ──


def tr(clave: str, lang: str = "es", **campos) -> str:
    """Texto de `clave` en el idioma pedido (español si no existe), con los campos rellenados."""
    fila = _T.get(clave)
    if fila is None:
        return clave
    texto = fila[_IDX.get(lang, 0)] if isinstance(fila, tuple) else fila
    return texto.format(**campos) if campos else texto


def claves() -> list:
    return sorted(_T)


__all__ = ["CONCEPTOS", "IDIOMAS", "claves", "tr", "tr_concepto"]
