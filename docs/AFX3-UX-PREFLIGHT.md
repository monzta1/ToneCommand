# TC FX3 controles voor de gebruikerstest

Op 17 oktober 2026 zijn de vier afgesproken controles uitgevoerd voor de
gebruikerssessie. De testversie wordt geidentificeerd door de commit in de
TC-voettekst. De volledige gebruikerstest en luistertest blijven afzonderlijk;
de publicatiestappen beginnen daarna.

## Foutscenario's

De Chrome-test gebruikt gesimuleerde API-antwoorden en blokkeert daarmee echte
AI- en hardwareaanroepen. De volgende situaties zijn gecontroleerd:

- Een geweigerd AI-voorstel en een mislukte statusuitlezing.
- Geen netwerkantwoord bij het plannen of verzenden.
- Een ongeldig serverantwoord en een niet-verbonden apparaat.
- Een niet-verifieerbare route en een niet-ondersteunde routekeuze.
- Een gedeeltelijk mislukte verzending met een terugleesfout.

Fouten in de algemene workflow krijgen een volledig leesbaar meldingsvak boven
de voettekst. Verzoektekst blijft behouden. Na een onbekend netwerkantwoord
staat de verbinding lokaal als onbevestigd en is een nieuwe statuscontrole
nodig. Een fout wist de oude verzendtoestemming; TC verstuurt niet automatisch
opnieuw en voert geen automatische opslag of NAM-installatie uit.

## Leesbaarheid

De extra tests gebruiken een lang verzoek, een uitgebreid plan, acht scenes en
een lijst met tweehonderd wijzigingen. De schermmaten zijn 1180 bij 720,
1280 bij 720, 1440 bij 900 en 1920 bij 1080 pixels. Conversatie, routekeuze en
verzoek overlappen niet; de hoofdknop en de laatste wijziging zijn bereikbaar.
Brede tabellen kunnen binnen hun eigen veld horizontaal scrollen. Een smalle
telefoonweergave blijft buiten de ondersteunde desktopinterface.

Bij een kort venster kan het verzoekgedeelte zelf verticaal scrollen, ook als
ontwerpopties en een foutmelding tegelijk openstaan. De vaste bovenbalk en
voettekst blijven daarbij op hun plek.

## Bediening

- Enter in de verzoektekst maakt een nieuwe regel; Tab bereikt de hoofdknop.
- De samenvattingen zijn met het toetsenbord in en uit te klappen zonder
  tekstverlies. CHOOSE ROUTE brengt de focus naar de routekeuze.
- Tijdens een lopende AI-aanvraag zijn reset, tekstinvoer en stapnavigatie
  geblokkeerd, zodat een laat antwoord niet in een ander ontwerp belandt.
- Het selecteren van FM9 maakt OPEN FM9 beschikbaar, ook als FX3 verbonden is.
  De keuze alleen wisselt de verbinding niet. Bij aanwezige tekst volgt eerst
  een waarschuwing dat deze niet wordt meegenomen; annuleren behoudt de tekst.
- De FM9-overgang is getest met een gesimuleerd ontkoppelantwoord en een
  bestemmingspagina. Dit is geen nieuwe test op een fysiek FM9-apparaat.

## Documentatie

Het [gebruikerslog](AFX3-GEBRUIKERSLOG.md) en de
[testvolgorde](AFX3-UX-USER-TEST.md) gebruiken dezelfde knopnamen en scheiden
voorstel, routekeuze, verzenden, NAM-installatie en permanent opslaan.
Lokale documentlinks worden gecontroleerd. De
[MK1-opdracht](AFX3-MK1-NAM-TEST.md) blijft een apart vervolgtraject.

## Afbakening van deze controle

De gecombineerde regressierun in simulatormodus slaagt met 203 tests. Een
aanvullende run van de verplichte controles en UI-tests slaagt met 58 tests.
Deze suites overlappen. De uitgebreide Chrome-workflowtest slaagt ook na de
laatste wijziging aan het scrollgedrag; JavaScript-syntax en lokale documentlinks
zijn gecontroleerd.

Er zijn geen nieuwe Fractal-parameterwrites, presetopslag of NAM-installaties
voor deze UX-controle uitgevoerd. De live interface wordt na de normale
herstart alleen-lezen gecontroleerd op bronversie, bediening en weergave.
Simulator- en browsertests verruimen geen apparaatmogelijkheden of veiligheidsgrenzen.

## Verzoekverduidelijking op 18 oktober 2026

Het Steve Vai-verzoek met vier scenes, hoge wah-pitch en External 2 is een extra
regressie in de Chrome-test. TC neemt vier scenes over, vraagt eerst naar wah
versus echte pitch en vraagt na de routekeuze of het niet-ondersteunde onderdeel
mag worden uitgesteld. Zonder antwoord volgen geen planacties. Een bewuste
uitstelkeuze wordt zichtbaar in de planwaarschuwingen. Tekstwijzigingen wissen
oude antwoorden. Een geweigerd ontwerp keert terug naar het verzoek zonder
SEND-token of automatische schrijfpoging.

Deze controles gebruiken gesimuleerde AI- en apparaatantwoorden. De intake-API
wordt afzonderlijk getest op actuele doelcontrole, strikte antwoorden, geen
AI-aanroep voor vereiste verduidelijking en ongewijzigde schrijfbeveiligingen.

De uitgebreide regressierun slaagt met 367 tests. De gerichte intake-,
scene-intentie- en routetests slagen met 74 tests, inclusief een onleesbare
doelpreset. Deze runs overlappen. De uitgebreide Chrome-test slaagt inclusief
bewuste sceneaantalwijziging, wisselen tussen AMP/CAB en NAM en het wissen van
oude uitstelkeuzes bij een routewissel. De vraagweergave is visueel gecontroleerd.

De eigenaar beoordeelt vervolgens of de workflow begrijpelijk is en het
muzikale resultaat voldoet. Registreer dat resultaat pas na de daadwerkelijke
test in het gebruikerslog. Wijzig de testversie niet tussentijds zonder dit
uitdrukkelijk af te spreken.

## Algemene AI vragen en antwoorden

De extra browsertest gebruikt een vraag over breedte en een vervolgvraag over
ritme of solo. Vrije antwoorden, suggesties zonder automatische verzending,
Enter als nieuwe regel, leeg antwoordveld, behoud van het oorspronkelijke
verzoek en leesbare gesprekshistorie worden gecontroleerd. HTML-achtige
antwoordtekst blijft gewone tekst. Een gewijzigd verzoek neemt geen oude
gesprekscode of antwoorden mee.

De API-tests controleren dat vragen geen acties of SEND-token bevatten, dat
antwoorden alleen bij de bijbehorende servervragen worden geaccepteerd en dat
een gewijzigde presetstatus het gesprek stopt. Een afgewezen ontwerp kan een
AI-vervolgvraag opleveren, maar wordt niet uitgevoerd. De apparaatcompiler,
uitvoeringscontrole en afzonderlijke opslagtoestemming blijven verplicht.

De gecombineerde regressierun slaagt met 392 tests. De gerichte dialoogtests
slagen met 27 tests, inclusief vervolgvraag, verlopen of verwisseld gesprek,
afgewezen ontwerp en gesprekscode die niet als SEND-token kan worden gebruikt.
Deze runs overlappen. De Chrome-test slaagt ook voor het behouden van een
antwoord als concept bij een verlopen gesprek, zonder automatische herhaling.

De gedeelde plannerfunctie wordt afzonderlijk getest voor routevragen,
ontwerpvragen en de herstelvraag na afwijzing. Het gedeelde veld `clarification`
blijft tekst; de gestructureerde FX3-vraag staat in een apart veld. Daardoor
blijven de bestaande FM9-kwaliteitscontrole en transportcode ongewijzigd.
De aansluitende run van verplichte controles en gerichte tests slaagt met
122 tests. Dit is een overlappende controle, geen extra aantal unieke tests.
