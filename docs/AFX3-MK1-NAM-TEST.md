# MK1 NAM verificatie als aparte vervolgopdracht

Status op 17 oktober 2026: geparkeerd op verzoek van de eigenaar. Eerst de
UX-gebruikerstest, daarna punten 4, 5 en 6 van het publicatieplan. Deze opdracht
start pas wanneer een MK1-tester beschikbaar is en instemt met de testgrenzen.
MK2-resultaten geven geen toestemming om MK1-installatie vrij te geven.

## Doel en afbakening

Verifieer de NAM-inventarisatie, installatie en modelselectie van TC op een
echte Axe-Fx III MK1. Hergebruik gedeelde code waar de metingen dat toelaten;
houd verschillen in geheugen en firmware in het FX3-apparaatprofiel.

Bij MK1 met NAM-firmware vervangt NAM de volledige User Cab Bank 2. MK2 heeft
apart NAM-geheugen. Voorbereiding is geen toestemming om firmware te upgraden
of een IR-bank te overschrijven. Zie [de geheugenregels](AFX3-CAB-INVENTORY.md).
De bestaande MK1-installatieblokkade blijft actief tot de acceptatie slaagt.

## Benodigde hulp van een MK1 eigenaar

- Geef uitvoering, exacte firmware, Axe-Edit-versie en besturingssysteem door.
- Maak relevante back-ups en bevestig dat externe audio volledig gedempt blijft.
- Wijs zelf een vrije testpreset en een vrij NAM-slot aan. Onze toestemming voor
  presets 321-329 en NAM-slots 250-256 op het MK2-testapparaat geldt hier niet.
- Geef afzonderlijk toestemming voor een permanente NAM-installatie en, later,
  het opslaan van de testpreset. Deel geen wachtwoorden of accountsleutels.

## Voorbereiding door de ontwikkelaar

Maak een begrensd testpakket met versie-identificatie, Nederlandstalige stappen
en export van meetresultaten. Algemene TC-diagnostiek bestaat al; de specifieke
MK1-opname en export moeten nog worden gebouwd. Een AI- of Tone3000-account is
niet nodig als een geschikt, rechtmatig deelbaar testmodel wordt meegeleverd.
Bundel geen firmware, editorbestanden, privemodellen of bankback-ups.

Het pakket mag geen MK2-opslagadressen of slotcapaciteit op MK1 aannemen. Laat
de technische controle mislukken als identiteit, adressering of teruglezing niet
bewezen zijn. Alleen een expliciet vrijgegeven doel mag later schrijfbaar zijn;
verruim bestaande veiligheidsgrenzen niet als omweg.

## Fase 1 metingen zonder TC schrijfacties

1. Leg TC-versie, apparaatidentiteit en firmware vast.
2. Controleer welke uitleescommando's op dit MK1-profiel verantwoord bruikbaar
   zijn. Onbewezen commando's worden niet automatisch uitgeprobeerd.
3. Neem afgesproken Axe-Edit-handelingen gericht op met tijdstippen en stapnamen.
   Gebruik niet gelijktijdig twee toepassingen als eigenaar van dezelfde MIDI-poort.
4. Vergelijk de NAM-slotinformatie met screenshots van Axe-Edit.
5. Laat de ontwikkelaar de opname beoordelen voordat een schrijfversie volgt.

## Fase 2 afzonderlijk toegestane schrijftest

1. Lees doelidentiteit en relevante toestand opnieuw uit; bevestig het gekozen
   slot en de toestemming. Gebruik een lege testpreset en gedempte externe audio.
2. Installeer een ondersteunde capture uitsluitend in het vrijgegeven NAM-slot.
3. Vergelijk de volledige teruggelezen inhoud met het verwachte resultaat.
   Controleer ook behoud van andere relevante geheugeninhoud.
4. Selecteer de capture via TC in een NAM-blok en vergelijk onafhankelijk met
   Axe-Edit. Geef de MIDI-poort steeds eerst vrij.
5. Sla de testpreset alleen met aparte toestemming op, laad opnieuw en controleer
   de verwijzing. Laat de eigenaar pas daarna op laag fysiek volume luisteren.

Stop bij een afwijking of onbekend schrijfresultaat. Geen automatische retry,
alternatieve opcode, rollback, firmwarewijziging of presetreload als herstelactie.
Verwijder het testmodel niet automatisch na afloop.

## Resultaten delen

Laat de tester een lokale ZIP vooraf bekijken. Voeg een samenvatting in JSON of
tekst toe met versies, stappen, tijdstippen, toestemmingen, resultaten, hashes en
foutmeldingen. Voeg alleen gerichte protocolopnamen en afgesproken screenshots
toe. Ook slotnamen en screenshots kunnen persoonlijke informatie bevatten.

Verwijder tokens, sleutels, accountgegevens, onnodige serienummers en lokale
gebruikerspaden. Deel geen volledige presetbanken of NAM-modelinhoud. Hashes
zijn voldoende voor inhoudsvergelijking buiten het apparaat. Upload niets
automatisch. Deel het gecontroleerde pakket via een bijlage in dit gesprek of
een afgesproken privelocatie; zet ruwe opnamen niet standaard in een GitHub-issue.

## Voorwaarden voor afronding

Inventarisatie, volledige teruglezing, behoud van andere inhoud, onafhankelijke
editorvergelijking en de toegestane presetopslag moeten aantoonbaar slagen op
de exacte geteste MK1/firmwarecombinatie. Leg eventuele restpunten vast en geef
alleen dat profiel vrij. Een pass op een MK1 bewijst geen andere firmware of
ander besturingssysteem.
