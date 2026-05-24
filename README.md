# Port Royale 2 — Trade Routes Maker

Editor per le rotte commerciali (`.ahr`) di **Port Royale 2 — Impero & Pirati**.
Decodifica/codifica del formato, builder JSON → `.ahr`, e una GUI desktop per creare/modificare rotte senza toccare il gioco.

## Stato

- ✅ Formato `.ahr` completamente decifrato (header, esclusioni rotta, azioni per merce, modalità carico/scarico, quantità, prezzi-soglia, città+magazzino).
- ✅ Mapping completo: 60 città (id 0-59 con nome, nazione, ruolo V/G, merci prodotte), 20 merci (id 0-19 con nome, prezzi min/mercato/max, prezzi consigliati buy/sell).
- ✅ Encoder/decoder Python con roundtrip byte-perfect (15 file di test).
- ✅ Builder da JSON user-friendly a `.ahr`, validato in-game.
- ✅ GUI PySide6 in stile tabellare con editing inline di tutte le merci.
- 🚧 Packaging in `.exe` Windows standalone via PyInstaller.

## Layout della cartella

```
.
├── ahr.py                    # decoder/encoder/builder + CLI
├── gui.py                    # GUI desktop PySide6
├── pr2_config.json           # config statico: 20 merci + 60 città (read-only)
├── user_state.json           # stato locale utente (gitignored)
├── README.md
├── port-royal2-2-map.jpg     # mappa di riferimento
├── icons/                    # icone merci (segnaposti francesi da elzetia.com)
└── rotte/
    ├── input/                # rotte .ahr esportate dal gioco (gitignored)
    ├── parsed/               # JSON decodificati (gitignored, derivati)
    ├── built/                # output del builder (gitignored, derivati)
    ├── build/                # spec JSON user-friendly per il builder
    │   └── example-route.json
    └── test/                 # fixture .ahr per regression test
        └── fixture_rotta01.ahr
```

## Uso CLI (`ahr.py`)

```bash
# Decodifica un .ahr in JSON ispezionabile
python ahr.py decode "rotta.ahr" "rotta.json"

# Da JSON-raw (output di decode) a .ahr
python ahr.py encode "rotta.json" "rotta.ahr"

# Da JSON user-friendly a .ahr (vedi rotte/build/example-route.json)
python ahr.py build "spec.json" "rotta.ahr"

# Roundtrip identity check
python ahr.py roundtrip "rotta.ahr"

# Lista i city_id degli stop (annotati con nomi se pr2_config.json è presente)
python ahr.py cities "rotta.ahr"

# Decodifica tutti i .ahr di una cartella
python ahr.py decode-dir rotte/input rotte/parsed

# Regression test (roundtrip su tutti i .ahr di una cartella)
python ahr.py test rotte/test
```

## Uso GUI (`gui.py`)

```bash
pip install PySide6
python gui.py
```

Interfaccia in italiano con:
- Pannello stop (drag-drop per riordinare) + esclusioni globali
- Tabella merci 20×N editabile inline: azione (auto/excluded/manual), carica (mode/qty/prezzo), scarica idem
- Bottoni 💰 prezzi consigliati con modificatori Ctrl/Shift
- Context menu su prezzo (Min/Mercato/Max), su merce (copia/incolla/reset), su stop (copia/incolla)
- `Ctrl+S` / `Ctrl+Shift+S` per salvataggio

## Formato `.ahr` (sintesi)

```
Header (11 byte):
  magic        4 byte   = 0x41 0x04 0x00 0x00 ("A" + 0x04)
  nstops       1 byte   numero stop (1-16)
  capacity     1 byte   ceil(nstops/4)*4, cap 16
  bitmap       5 byte   esclusioni rotta (1 bit = 1 merce attiva)

Stop (426 byte, ripetuto per nstops volte):
  display_order   20 byte    permutazione 0..19 (manuali in cima nell'UI)
  actions[20]     u32 LE     0=excluded, 1=auto, 2=manual
  trades[20]      16 byte/cad:
    load_price    u32 LE     soglia città (oro/ton); 0xFFFFFFFF = "con magazzino"
    load_qty      u16 LE     quantità (0xFFFF = "max")
    load_aux      u16 LE     residuo snapshot, preservato per roundtrip
    unload_price  u32 LE     idem per scarico
    unload_qty    u16 LE
    unload_aux    u16 LE
  trailer         6 byte     city_id, 0x00, 0x21, 0x00, start_flag, 0x00
```

## Note

- Le città cambiano nazione durante la partita: il campo `nation` in `pr2_config.json` è la nazione iniziale al nuovo gioco. Gli override per la partita corrente vivono in `user_state.json` (gitignored).
- I prezzi "consigliati" buy/sell per merce sono definiti globalmente in `pr2_config.json` e possono essere sovrascritti per singola città in `user_state.json`.
- Le icone delle merci sono prese da [elzetia.com](https://elzetia.com) — sono in francese, alcune sono usate come segnaposto per le merci specifiche di P.R.2 (Spezie, Vino, Coloni).
