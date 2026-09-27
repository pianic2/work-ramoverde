# RamoVerde — comparatore di direzioni visuali

## Scopo

Questo esperimento mette a confronto dieci linguaggi UI applicati agli stessi contenuti. Serve allo stakeholder per valutare concretamente stile, tipografia, colore, composizione, componenti e percorso di richiesta. Non è il sito definitivo.

## Fonte canonica e limiti

I contenuti seguono la Source of Truth **WRM-CLIENT-SOT** e i dati confermati inclusi nel brief del progetto. I prototipi non aggiungono recapiti, prezzi, recensioni o promesse. Le qualifiche ISO 9001 e SOA V categoria sono indicate come dichiarate dall’azienda e da verificare prima della pubblicazione. Le illustrazioni e le gallery sono placeholder dimostrativi, non lavori attribuiti a RamoVerde.

Palette, tipografia, proporzioni, immagini, componenti, animazioni e composizioni sono ipotesi visuali per la valutazione: **non sono decisioni definitive del brand**. Nessuna proposta è una raccomandazione o un vincitore.

## Le dieci alternative

1. `design-01-professional/` — Corporate contemporaneo, griglia rigorosa e spazio bianco.
2. `design-02-technical/` — Servizi tecnici, procedure e maggiore densità informativa.
3. `design-03-editorial/` — Impaginazione editoriale e immagini in primo piano.
4. `design-04-institutional/` — Geometria sobria e qualifiche facilmente leggibili.
5. `design-05-field-operations/` — Lavoro sul campo, numerazioni e sequenze operative.
6. `design-06-modern-landscaping/` — Composizioni immersive e interazioni contemporanee.
7. `design-07-green-grid/` — Componenti modulari e sistema a griglia.
8. `design-08-local-trust/` — Tono diretto, persone e contatti accessibili.
9. `design-09-infrastructure/` — Servizi strutturati per committenti organizzati.
10. `design-10-conversion-first/` — Percorso guidato dalla scelta del servizio alla richiesta.

## Apertura

Aprire `index.html` con un browser per confrontare le dieci proposte. Ogni pulsante apre la demo completa nella rispettiva cartella. È possibile aprire direttamente qualsiasi `design-XX-*/index.html` dal filesystem. Non è necessario alcun build step; per un server statico, dalla cartella del comparatore eseguire `python3 -m http.server 8000` e aprire `http://localhost:8000`.

## Struttura

```text
index.html
README.md
design-01-professional/
...
design-10-conversion-first/
```

Ogni variante è indipendente e contiene i propri file e stili. Le pagine sono progettate per viewport mobile, tablet e desktop; il modulo è dimostrativo e non invia dati.
