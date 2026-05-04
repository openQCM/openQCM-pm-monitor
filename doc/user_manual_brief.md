# Brief per la realizzazione del manuale utente — openQCM-pm-monitor

> **Istruzioni per l'AI**: usa questo file come specifica per generare un
> manuale utente del software **openQCM-pm-monitor**. Il manuale è destinato
> all'**utente finale**, non al programmatore. Genera l'output in **inglese**
> (American English), come **documento Microsoft Word (`.docx`)** già
> impaginato e pronto per la stampa.

---

## 1. Contesto del prodotto

**openQCM-pm-monitor** è un software desktop (Windows) per il campionamento del
particolato atmosferico (PM — Particulate Matter) con tecnologia QCM-D
(Quartz Crystal Microbalance with Dissipation). Pilota lo strumento
**openQCM Q-1 PM Aerosol Head**, un campionatore inerziale che convoglia l'aria
ambiente attraverso un ugello fino a un cristallo di quarzo, sul quale le
particelle si depositano per inerzia. La variazione della frequenza di
risonanza del quarzo, misurata in tempo reale, è proporzionale alla massa
depositata (equazione di Sauerbrey). Combinata con la portata d'aria
campionata, fornisce la **concentrazione di particolato in µg/m³**.

### Componenti hardware governati dal software
- Cristallo QCM (5 MHz o 10 MHz, AT-cut)
- Microcontrollore Teensy 4.0 (firmware v0.2.2-PM)
- Pompa di aspirazione con controllo PWM
- Sensore di velocità aria FS3000 (Renesas, MEMS termopila)
- Controllore TEC MTD415T (stabilizzazione termica del cristallo)

### Pubblico del manuale
- **Tecnico di laboratorio** o **operatore strumentale** che usa il programma
  per acquisizioni di routine
- Conosce il dominio (campionamento aria, QCM-D di base) ma non è uno
  sviluppatore software
- Lavora su Windows 10/11

---

## 2. Tono e stile richiesti

- **Inglese tecnico, chiaro e diretto** ("click the button", "open the
  dialog", "the pump aspirates air through the crystal")
- Frasi brevi, paragrafi corti
- Voce attiva ovunque possibile
- **Numerare le procedure** quando l'ordine è importante
- Evitare gergo da sviluppatore (no "QThread", "signal", "mutex" ecc.)
- Spiegare i parametri fisici in modo accessibile per l'operatore di
  laboratorio (es. *"Pumping time: how long the pump draws air through
  the crystal"*)
- Includere note di **avvertenza** (Caution / Warning) dove rilevante
  (es. *"Do not disconnect the serial cable during an active cycle"*)
- Includere **suggerimenti operativi** (Tip / Note) dove sensato
  (es. *"For fine particulate matter, set a pumping time of at least
  5 minutes"*)
- Usare **British English** o **American English** in modo coerente
  (consigliato American English, più diffuso in ambito strumentale)

---

## 3. Output richiesto

- **Lingua**: **English (American English preferred)**
- **Formato**: **Microsoft Word `.docx`** già impaginato (non Markdown grezzo)
- **Nome file di output**: `openQCM-pm-monitor_user_manual.docx`
- **Lunghezza target**: 25–40 pagine A4 a stile standard

### Requisiti di impaginazione del file .docx

- **Pagina**: A4, margini 2.5 cm
- **Font corpo**: Calibri 11 pt (o Arial 11 pt) — *single line spacing*
- **Titoli**: usare gli stili Word nativi `Heading 1`, `Heading 2`, `Heading 3`
  (così la generazione del Sommario è automatica)
- **Sommario (Table of Contents)** all'inizio, generato dagli stili Heading
- **Numero di pagina** in piè di pagina (centrato)
- **Intestazione** con il nome del documento e la versione del software
  (es. "openQCM-pm-monitor — User Manual — v1.0.0")
- **Caption** automatiche per figure e tabelle (`Figure N — …`, `Table N — …`)
- Per **comandi seriali** o esempi tecnici brevi, usare lo stile carattere
  monospace (Consolas 10 pt) o lo stile paragrafo "Code"
- **Avvertenze e suggerimenti**: usare callout box visivi (es. tabella a una
  cella con sfondo grigio chiaro) etichettati `Note`, `Tip`, `Caution`,
  `Warning`
- **Indice delle figure** e **indice delle tabelle** alla fine del documento

### Cosa fornire alla consegna

L'AI genera **un solo file**:
- `openQCM-pm-monitor_user_manual.docx`

Gli screenshot reali NON sono inclusi (non disponibili per l'AI). Vanno
inseriti dei **placeholder** in formato visibile dentro il `.docx`:
una tabella a una cella, larga circa 10 cm, con bordo nero e dentro
il testo (in italico, grigio):

```
[ Inserire qui Figura N — screenshots/<nome-file>.png ]
[ Caption: <didascalia indicata sotto> ]
```

L'utente sostituirà manualmente questi placeholder con `Insert → Pictures`
in Word, mantenendo le caption.

---

## 4. Riferimenti tecnici da consultare

L'AI può attingere ai seguenti file del repository
[https://github.com/openQCM/openQCM-pm-monitor](https://github.com/openQCM/openQCM-pm-monitor) per estrarre informazioni accurate:

| File | Cosa contiene |
|------|---------------|
| `README.md` | Panoramica funzionale, formato CSV, formule, struttura progetto |
| `CHANGELOG.md` | Cronologia delle feature |
| `doc/flow_calculation_spec.md` | Specifica tecnica del calcolo flusso/concentrazione |
| `openqcm/constants.py` | Costanti fisiche (Sauerbrey, default) |
| `openqcm/gui/main_window.py` | Logica della GUI (ma evitare di descrivere il codice — solo i comportamenti visibili) |

⚠️ **Nota**: l'AI deve descrivere solo ciò che l'utente vede e tocca. **Non**
descrivere implementazioni interne (thread, lock, eventi Qt, ecc.).

---

## 5. Indice suggerito del manuale

```
1. Introduzione
   1.1 Cosa fa openQCM-pm-monitor
   1.2 Requisiti hardware e software
   1.3 Convenzioni di questo manuale

2. Installazione
   2.1 Requisiti di sistema
   2.2 Installazione del driver Teensy
   2.3 Installazione dell'applicazione (file .exe)
   2.4 Primo avvio

3. Panoramica dell'interfaccia grafica
   3.1 Layout generale (pannelli sinistro / centrale / destro)
   3.2 Barra delle metriche (le sette card numeriche)
   3.3 Schede principali: Monitoring, Sweep, Console
   3.4 Indicatori di stato (TEC, hardware, sampling time)

4. Procedura operativa di base
   4.1 Connessione al dispositivo
   4.2 Selezione del cristallo (5 MHz / 10 MHz)
   4.3 Ricerca del picco di risonanza (Find Peak)
   4.4 Avvio del monitoraggio continuo (Start Monitor)
   4.5 Interruzione del monitoraggio

5. Misura della concentrazione di particolato (Cycle)
   5.1 Concetto: ciclo REFERENCE → PUMP_ON → WAITING
   5.2 Configurazione dei tempi (pump-on, waiting)
   5.3 Calibrazione del flusso: modalità Analitica e Calibrata
   5.4 Avvio del ciclo (Start Cycle)
   5.5 Interpretazione delle barre di concentrazione e massa
   5.6 Salvataggio dei dati e formato dei file CSV
   5.7 Best practice per misure attendibili

6. Controllo della temperatura (TEC)
   6.1 Quando attivare il TEC
   6.2 Impostazione del setpoint
   6.3 Significato degli stati (Inactive, Approaching, In target, Error)
   6.4 Reset in caso di errore

7. Lettura ed esportazione dei dati
   7.1 La cartella `data/` accanto all'eseguibile
   7.2 File del monitoraggio (raw)
   7.3 File del ciclo (per-cycle results)
   7.4 Apertura dei CSV in Excel / Origin / pandas
   7.5 Glossario delle colonne con unità di misura

8. Strumenti diagnostici
   8.1 La scheda Sweep (visualizzazione del picco)
   8.2 La scheda Console (comandi seriali avanzati)
   8.3 Lettura dello stato del TEC (registro errori MTD415T)

9. Risoluzione dei problemi (Troubleshooting)
   9.1 La porta seriale non viene rilevata
   9.2 Errore "TEC Error" persistente
   9.3 Picco non trovato durante Find Peak
   9.4 La pompa non parte
   9.5 Velocità del flusso a zero durante il ciclo
   9.6 Salvataggio CSV interrotto

10. Appendice A — Tabella dei comandi seriali (utenti avanzati)

11. Appendice B — Specifiche fisiche
   - Equazione di Sauerbrey
   - Calcolo della dissipazione (-3 dB)
   - Calcolo di portata e concentrazione

12. Appendice C — Crediti e licenza
```

---

## 6. Screenshot richiesti

⚠️ **Per ogni screenshot indicato sotto, nel `.docx` l'AI deve inserire un
placeholder visivo: una tabella 1×1 (larghezza ~10 cm, bordo nero sottile)
contenente le seguenti righe in italico grigio:**

```
[ Insert here Figure N — screenshots/<file-name>.png ]
[ Caption: <didascalia indicata sotto> ]
```

Subito sotto la tabella, una riga con caption in stile Word
"Caption" / "Figure":

> **Figure N** — *Didascalia descrittiva* (corsivo, 10 pt)

L'utente sostituirà ciascun placeholder facendo `Insert → Pictures →
This Device…` in Word, scegliendo l'immagine in `doc/screenshots/`,
e cancellerà la tabella di placeholder. La caption rimane.

### Lista degli screenshot necessari

| # | Nome file | Cosa deve mostrare | Sezione del manuale |
|---|-----------|--------------------|---------------------|
| 1 | `screenshots/01_first_launch.png` | Schermata iniziale completa subito dopo l'apertura, prima della connessione | §3.1 |
| 2 | `screenshots/02_metric_cards.png` | Dettaglio della riga di sette card metriche in alto (Frequency, Dissipation, Mass, Concentration, Velocity, Flow Rate, Temp) | §3.2 |
| 3 | `screenshots/03_left_panel.png` | Pannello sinistro intero con i gruppi Connection / Plot Control / Peak Detection / Continuous Measurement / Pump Cycle Procedure | §3.1 |
| 4 | `screenshots/04_right_panel.png` | Pannello destro intero con Temperature Control e Pump & Flow | §3.1 |
| 5 | `screenshots/05_connection_group.png` | Dettaglio del gruppo Connection con porta selezionata e stato "Connected" | §4.1 |
| 6 | `screenshots/06_find_peak_result.png` | Scheda Sweep dopo Find Peak con curva di guadagno, marker stella, banda −3 dB evidenziata | §4.3 |
| 7 | `screenshots/07_monitoring_active.png` | Scheda Monitoring durante un monitoraggio attivo con grafici Frequency/Dissipation in scorrimento | §4.4 |
| 8 | `screenshots/08_cycle_running.png` | Scheda Monitoring durante un ciclo attivo: barra "Cycle: PUMP ON Xs left" visibile e dati di un ciclo già completato sui plot di sotto | §5.4 |
| 9 | `screenshots/09_cycle_results_plots.png` | Riga inferiore di plot: Δm/cycle, Concentration/cycle, Δf/ΔD/cycle, trend Freq/Diss | §5.5 |
| 10 | `screenshots/10_flow_calibration.png` | Sezione "Flow calibration" del pannello Pump & Flow con modalità Analytical e Calibrated | §5.3 |
| 11 | `screenshots/11_tec_states.png` | Pannello Temperature Control con TEC in stato "In target" (verde) | §6.3 |
| 12 | `screenshots/12_tec_setpoint.png` | Dettaglio del controllo Temperature Set con valore in °C | §6.2 |
| 13 | `screenshots/13_save_dialog.png` | Finestra di dialogo "Save monitoring data as..." con la cartella `data/` selezionata | §7.1 |
| 14 | `screenshots/14_csv_in_excel.png` | Esempio del file CSV aperto in Microsoft Excel, con header `frequency_Hz`, `dissipation_ppm`, ecc. visibili | §7.4 |
| 15 | `screenshots/15_csv_cycle_in_excel.png` | Esempio del file CSV per-cycle aperto in Excel con `concentration_ug_m3` evidenziato | §7.3 |
| 16 | `screenshots/16_console_tab.png` | Scheda Console con qualche comando inviato e risposta dal Teensy | §8.2 |
| 17 | `screenshots/17_context_menu.png` | Plot con il menu contestuale custom aperto (Auto-scale / Reset Zoom / Pan Mode / Select Mode) | §3.3 |
| 18 | `screenshots/18_pump_disabled_during_cycle.png` | Pannello Pump & Flow con tutti i controlli (Start, Stop, preset, slider) in stato disabilitato durante un ciclo attivo | §5.4 |

⚠️ **Importante**:
- Gli screenshot devono essere catturati con la versione **1.0.0** del software
- Risoluzione minima 1280×720, preferibilmente 1920×1080
- Evidenziare con frecce/cerchi rossi gli elementi citati nel testo solo dove utile (l'AI può suggerirlo nelle didascalie ma l'inserimento è a cura dell'utente)

---

## 7. Glossario obbligatorio

L'AI deve includere un glossario in coda al manuale che spieghi in italiano,
con frasi brevi adatte a un operatore di laboratorio (non a uno sviluppatore),
i seguenti termini:

- QCM, QCM-D
- AT-cut, frequenza di risonanza, dissipazione
- Cristallo a 5 MHz vs 10 MHz: implicazioni per la sensibilità
- Equazione di Sauerbrey
- Q-factor, banda a metà potenza (-3 dB)
- TEC (Thermoelectric Cooler), setpoint
- ppm (parts per million)
- Portata volumetrica vs velocità
- Particolato (PM, µg/m³)
- Ciclo di misura: reference, pump, waiting

---

## 8. Procedure passo-passo da includere

Per ognuna delle seguenti procedure, l'AI deve scrivere una versione passo-
passo numerata, esplicita, con prerequisiti e risultato atteso:

1. **Prima accensione e connessione** (con screenshot 1, 5)
2. **Esecuzione del Find Peak** (con screenshot 6)
3. **Avvio di un monitoraggio semplice di 30 minuti** (con screenshot 7)
4. **Esecuzione di un ciclo completo di campionamento PM** (con screenshot 8, 9, 13)
5. **Calibrazione del flusso con flussimetro di riferimento** (con screenshot 10)
6. **Lettura del CSV di un ciclo concluso in Excel** (con screenshot 14, 15)
7. **Risoluzione di un errore TEC** (con screenshot 11, 16)

---

## 9. Note finali per l'AI

- **Lingua**: il manuale è in **English (American)**. Tutto il contenuto,
  inclusi callout, didascalie, voci di indice e glossario.
- **Non** inserire blocchi di codice Python o C++ nel manuale (è un manuale
  utente, non per sviluppatori).
- **Includere** i comandi seriali raw solo nell'Appendice A, mai nel corpo
  principale.
- **Citare** le unità di misura ovunque siano rilevanti.
- **Mantenere** le formule fisiche solo nelle appendici (B).
- **Includere** una nota in §1 che dice: *"For technical questions, consult
  the README.md in the GitHub repository or contact Novaetech S.r.l."*
- **Numerare** tutte le figure (`Figure 1`, `Figure 2`, …) usando il sistema
  di caption automatiche di Word.
- **Numerare** le tabelle allo stesso modo (`Table 1`, `Table 2`, …).
- **Sommario / Table of Contents**: generato dagli stili Heading; deve
  apparire come prima pagina dopo la copertina.
- **Indici** in coda al documento: List of Figures, List of Tables.

Output finale atteso: un singolo file
`openQCM-pm-monitor_user_manual.docx` pronto per essere revisionato
dall'utente, con i placeholder degli screenshot già inseriti.
