# TC Axe-Fx III gebruikerslog

Concept voor GitHub, bijgewerkt op 18 oktober 2026. Dit log beschrijft de
gebruikersfuncties en bekende beperkingen van de FX3-integratie op basis van
TC 1.5.15. De integratie is nog niet als publieke release gepubliceerd.

De huidige FW33-schrijfondersteuning is getest op een Axe-Fx III MK2 met exact
firmware `33.00-beta.20261006`, Windows, Python 3.12 en de mido MIDI-backend.
Ondersteuning voor andere apparaten, firmwareversies of besturingssystemen volgt
niet automatisch uit deze tests. Het afzonderlijke FW32.06-profiel behoudt zijn
eigen grenzen.

## Wijzigingen op 18 oktober 2026

### Klankverschillen tussen scenes controleren

Bij een nieuw AMP/CAB-verzoek met meerdere scenes legt TC eerst de muzikale
functie en het gewenste verschil per scene vast. Daarna werkt de AI de
instellingen uit. Het ontwerp mag deze eerdere afspraken niet achteraf
aanpassen om een kopie als een nieuwe klank te presenteren. Exact hergebruik
vereist een onderbouwing uit je eigen verzoek of antwoord. TC kan dezelfde
ampfamilie blijven gebruiken en toch een passende variatie uitwerken; andere
modellen kiezen is geen doel op zich.

In PLAN en REVIEW toont KLANKVERSCHILLEN EN HERGEBRUIK de concrete geplande
verschillen en de actieve IR-namen. Een andere naam, kanaalletter of alleen
meer volume geldt niet als een andere klankkleur. Pan wordt afzonderlijk als
ruimtelijk verschil beoordeeld. Kleine knopverschillen blijven herkenbaar als
onbewezen hoorbaar contrast. Ook Master, Depth en Presence staan nu in het
instellingenoverzicht; gedeelde delay- en choruskanalen zijn expliciet benoemd.

De cab-omschrijving wordt getoetst aan het formaat in de gekozen actieve
IR-namen. Staat er 2x12 in de naam, dan mag TC die selectie niet als een 4x12
beschrijven. Een User IR zonder die metadata bewijst geen kastformaat.
Een afgewezen voorstel mag de AI eenmaal zelf corrigeren binnen dezelfde
afspraken en veiligheidscontroles. Bestaande API-koppelingen blijven werken;
de bijgewerkte GUI schakelt de voorafgaande sceneafspraken in bij nieuwe
ontwerpen. Succesvol verzonden ontwerpen bewaren deze afspraken ook in de
lokale ontwerphistorie.

Deze controle vergelijkt parameters en is geen luistertest of bewijs dat een
opname exact wordt gereproduceerd. REVIEW, bevestigde externe mute, SEND en
permanent opslaan blijven afzonderlijke stappen.

### Bestaande functies behouden bij firmware updates

Het FW33-profiel bouwt voort op alle75 goedgekeurde FW32.06-parameters en voegt
acht parameters toe. De ontbrekende wah Control, elf PEQ-bedieningen en Pitch
Level zijn overgenomen met de gemeten FW33-aansturing. Ook eerder geteste
nulwaarden blijven beschikbaar; dat geeft geen toestemming om de veilige
bouwvolumes te verhogen. Regressietests bewaken dat nieuwe profielen geen
oude parameters stilzwijgend verliezen.

Bij een AMP/CAB-ontwerp kan TC nu Cry Babe op gedeeld kanaal A uitwerken,
per scene aan/uit zetten en aan External1 of2 met Off/Fast Pos koppelen. Kies
dit onder ONTWERPOPTIES of benoem een eenduidige External-keuze in je verzoek.
Een bestaande koppeling blijft behouden. Fast Pos kan bij pedaalbeweging ook
een scene met wah uit overrulen; kies Off als alleen scenes het effect moeten
schakelen. Een hoge wah-filterstand is geen echte pitchverhoging.

Onder CONTROLLERS kan Volume/Pan1 nu ook op FW33/MK2 aan External1 of2 worden
gekoppeld. Hiervoor zijn Type Volume,0dB op alle kanalen, de volledige
standaardcurve en Auto Engage Off vereist. De globale MIDI/CC-koppeling op je
apparaat wordt niet gewijzigd. De vaste AMP/CAB-bouwroute plaatst nog geen
Volume-blok.

Niet elke oude bouwmogelijkheid is hiermee al naar FW33 gebracht. Extra
effectmodellen, blokinstanties/kanalen, flexibele ketens, PEQ/Pitch-inpassing,
Reverb en meerdere Delay-voicings in AMP/CAB, en exact raw Undo staan apart
in het [migratieoverzicht](AFX3-FIRMWARE-MIGRATION.md). Een nieuwe, onbekende
firmware blijft alleen-lezen totdat de gewijzigde communicatie is gecontroleerd.

### Ontwerpen in gesprek met de AI

Bij een ondersteund AMP/CAB-ontwerp krijgt de AI expliciet de beschikbare
wah-controllerkeuzes en de uitgelezen bestaande koppeling mee. De AI levert de
wah-klank en scene-instellingen; TC voegt de gekozen External-koppeling toe.
Een ontbrekend controller-veld in het AI-ontwerp is dus geen ontbrekende
apparaatfunctie. Voordat een wah-verduidelijkingsvraag verschijnt, controleert
dezelfde AI die vraag eenmaal opnieuw tegen deze mogelijkheden en je eerdere
antwoorden. Een echte onduidelijkheid kan nog steeds een vraag opleveren.

Een afgewezen wah-ontwerp mag dezelfde AI eerst eenmaal zelf corrigeren binnen
de bestaande controles. Een eventuele vervolgvraag krijgt ook je eerdere
keuze voor wah-filter of echte pitch mee; die keuze hoeft niet opnieuw gemaakt
te worden. Dit herstel betreft alleen het voorstel, nooit een herhaalde
schrijfactie naar het apparaat.

Een eenduidig tekstverzoek zoals "wah op External 2, automatisch inschakelen"
wordt gebruikt als je geen aparte controllerkeuze hebt gemaakt. Een expliciete
keuze onder ONTWERPOPTIES gaat voor. "Behouden" schakelt Auto Engage niet in:
zonder bestaande koppeling krijgt een nieuwe native koppeling standaard Off.
Kies Fast Pos als je automatisch inschakelen door pedaalbeweging wilt.

De geselecteerde AI kan tijdens routeonderzoek en planbouw zelf een gerichte
vraag stellen over elke muzikale onduidelijkheid, tegenstrijdige wens of
ontbrekende mogelijkheid. Dit is niet beperkt tot de vaste wah- en scenevragen.
Zoals bij de FM9 is het uitgangspunt: eerst de wens verduidelijken, daarna het
voorstel. De FX3-uitvoering houdt haar eigen apparaatcontroles.

Onder TONECOMMAND HEEFT EEN VRAAG staat een leeg antwoordveld. Typ je antwoord
of kies een suggestie en klik VERSTUUR ANTWOORD. Een suggestie invullen verzendt
niets; Enter maakt een nieuwe regel. Eerdere vragen en antwoorden blijven
zichtbaar in DESIGN CONVERSATION en gaan mee naar het volgende ontwerp.

TC vraagt een ding tegelijk en krijgt instructies om duidelijke wensen zelf uit
te werken. Het gesprek is dus geen verplichte vragenlijst. De AI kiest gewone
amp-, cab- en effectinstellingen zelfstandig uit de beschikbare mogelijkheden.
Als een controle het ontwerp afwijst, mag dezelfde AI eenmalig een vraag over
een uitvoerbaar alternatief stellen. Een foutieve of mislukte AI-reactie kan
nog steeds tot een foutmelding leiden; er volgt geen automatische verzending.

Antwoorden horen bij het oorspronkelijke verzoek, apparaat en doelpreset.
Wijziging van die context maakt het gesprek ongeldig. Het gesprek blijft
tijdelijk in de lopende TC-sessie en is geen permanente gespreksopslag. Na
vijftien minuten verloopt de gesprekscode; na acht vraagrondes vraagt TC om een
nieuw verzoek met de gemaakte keuzes. Geen enkel antwoord geeft toestemming
voor onbewezen bediening, SEND, presetopslag of NAM-installatie.

### Het verzoek afstemmen voor de planbouw

TC herkent expliciete sceneaantallen in Nederlands en Engels, zoals `4 scenes`
of `vier scènes`. Controleer het overgenomen aantal in ONTWERPOPTIES. Bij
tegenstrijdige aantallen vraagt TC om een expliciete keuze. Een route die
minder scenes ondersteunt, mag het gevraagde aantal niet stilzwijgend verlagen.

Bij een verzoek om een wah met hoge pitch vraagt TC of je een hogere,
helderdere filterstand bedoelt of echte verhoging van de gespeelde toonhoogte.
Dat zijn verschillende effecten. Antwoord onder EVEN AFSTEMMEN en klik
VERDER MET MIJN ANTWOORDEN.

Als de gekozen bouwroute een verplicht onderdeel niet ondersteunt, kun je
expliciet kiezen om alleen het ondersteunde deel te laten ontwerpen. Uitgestelde
onderdelen blijven zichtbaar als NIET uitgevoerd in het voorstel. Zonder die
keuze bouwt TC geen gedeeltelijk ontwerp. Nieuwe FW33-wahbediening,
controllerkoppelingen en pitchverhoging worden hierdoor niet vrijgegeven.

Een ontwerp dat niet door de vereistencontrole komt, geeft een ontwerpbericht
zonder verzendbaar plan, niet de misleidende melding dat de AI-verbinding stuk
is. Het oorspronkelijke verzoek blijft behouden. Deze intake verzendt niets.

## Wijzigingen op 17 oktober 2026

### Duidelijker een ontwerp beginnen

- De interface gebruikt de gedeelde vormgeving van de oorspronkelijke TC.
  REQUEST, PLAN, REVIEW, CONFIRM en SEND blijven afzonderlijke stappen.
- Vul tekst of een audiolink in en klik GENERATE PLAN. Als routeonderzoek nodig
  is, begint TC daarmee en vraagt daarna om jouw keuze voor AMP/CAB of NAM.
- CHOOSE ROUTE brengt je naar de routekeuze. TC installeert geen NAM en bouwt
  geen preset alleen omdat een route wordt aanbevolen.
- Sceneaantal, bronsoort en controlleropties staan in een standaard ingeklapt
  veld. Het gekozen sceneaantal blijft zichtbaar in de kop.
- AMP LIBRARY, CAB LIBRARY en NAM / TONE3000 blijven rechts uitklapbaar.
- Enter maakt een nieuwe regel; de knop start het verzoek. In- en uitklappen
  van YOUR REQUEST behoudt de tekst.
- NEW DESIGN begint een schoon ontwerp na bevestiging als er al werk staat.
  Deze knop wist of herlaadt geen preset op de Fractal.
- Uitleg bij de volgende stap maakt duidelijk waarom een actie niet beschikbaar
  is. De verouderde tekst over uitsluitend NAM-slot 001 is verwijderd.
- Netwerkfouten en ongeldige serverantwoorden verschijnen volledig leesbaar in
  een apart meldingsvak. Het verzoek blijft behouden en oude verzendtoestemming
  vervalt; er volgt geen automatische nieuwe schrijfpoging.
- Bij selectie van FM9 wordt OPEN FM9 beschikbaar, ook als de FX3 verbonden is.
  Bij aanwezige verzoektekst waarschuwt TC voordat je de pagina verlaat.

### AMP en CAB ontwerpen binnen het geteste FW33 profiel

- De AI kan kiezen uit de firmwaregebonden lijst met 336 versterkermodellen.
  REFRESH AMP MODELS controleert de catalogus; onbekende nieuwe modellen worden
  niet automatisch schrijfbaar.
- De ingebouwde Factory-catalogus bevat 2048 namen. Importeer actuele namen van
  je Usercabs om die als keuzemogelijkheid beschikbaar te maken. Namen importeren
  installeert geen IR-audio en bewijst niet welke IR-inhoud op het apparaat staat.
- De geteste AMP/CAB-bouwer ondersteunt 1 tot en met 8 scenes, maximaal vier
  verschillende Amp/Cab-voicings op kanalen A-D en een mixer met vier IR-slots.
  Acht scenes betekenen niet acht onafhankelijke ampkanalen.
- De begrensde effectondersteuning omvat onder meer T808 Mod Drive, Modern VCA
  Compressor en 10 Band Variable Q. Dit is geen algemene vrijgave van alle
  effectmodellen, parameters of blokinstanties.
- Bij ondersteunde timinginstellingen controleert en zet TC Delay/Chorus Tempo
  op NONE voordat een letterlijke tijd of snelheid wordt geschreven. Dit geldt
  binnen de geverifieerde AMP/CAB-bouwroute, niet voor alle routes en modellen.
- Succesvol verzonden AMP/CAB-ontwerpen kunnen lokaal worden bewaard en na
  controle worden hervat. BIJSTUREN NA LUISTERTEST maakt een nieuw voorstel
  voor geselecteerde scenes; ook dat vereist opnieuw review en toestemming.

### NAM en audiobronnen

- Met een gekoppeld TONE3000-account kun je captures zoeken en een exact model
  kiezen. Native installatie ondersteunt het gemeten MK2-profiel en de
  ondersteunde A2-structuur; niet ieder aangeboden NAM-bestand is compatibel.
- TC kan NAM-slots 001-256 inventariseren. Je kiest zelf een toegestane
  installatiepositie en bevestigt permanent schrijven en eventueel overschrijven.
  De capture installeren en die in een preset selecteren zijn aparte handelingen.
- De NAM-bouwer begint vanuit een lege preset met één scene. Uitbreiden naar
  twee scenes op de ondersteunde bestaande NAM-route is afzonderlijk begrensd.
  De AMP/CAB-ondersteuning voor acht scenes geldt niet automatisch voor NAM.
- Op MK1 met NAM-firmware gebruikt NAM de volledige User Cab Bank 2; op MK2
  heeft NAM apart geheugen. MK1-installatie blijft geblokkeerd totdat de
  [aparte MK1-testopdracht](AFX3-MK1-NAM-TEST.md) slaagt voor het betreffende profiel.
- Een audiolink in het verzoek of een lokaal bestand kan als klankreferentie
  dienen. Fragmenten tot 60 seconden worden lokaal gemeten. Dit is geen directe
  AI-beluistering, gitaarisolatie of garantie op een identieke opnamesound.
- De optionele vergelijking met een eigen opname toont beschrijvende
  meetverschillen, geen automatische klankscore of volumeafregeling.

## Veilig verzenden en opslaan

Controleer de doelpreset en wijzigingen en demp externe audio voordat TC naar
het apparaat schrijft of presets/scenes wisselt. TC heeft geen audiolimiter en
biedt geen garantie tegen onverwachte luidheid of akoestische feedback.

SEND wijzigt de preset in het werkgeheugen. Permanent opslaan gebeurt apart,
met PREVIEW STORE en een eigen bevestiging voor de huidige toegestane positie.
NAM-installatie schrijft wel permanent naar gedeeld modelgeheugen en heeft
daarom een aparte bevestiging.

Een verificatiefout stopt de uitvoering; gedeeltelijke wijzigingen kunnen
achterblijven. Verzend bij een onbekend schrijfresultaat niet automatisch
opnieuw en herlaad de preset niet als automatische herstelpoging. Luister pas
na controle op laag fysiek volume. Sluit Axe-Edit wanneer TC de MIDI-poort
moet gebruiken.

## Bekende beperkingen

- Algemene vrije ketenbouw en Send/Return-routes zijn nog niet vrijgegeven in
  de normale planner. De huidige bouwers gebruiken begrensde, geteste routes.
- Nieuwe FW33-controllerkoppelingen, alle overige effectmodellen en extra
  blokinstanties zijn niet algemeen ondersteund. Globale pedaal- en MIDI
  CC-toewijzingen blijven de verantwoordelijkheid van de gebruiker.
- Een willekeurige bestaande preset kan nog niet automatisch als volledig
  gecontroleerd TC-ontwerp worden overgenomen.
- Algemene Save As naar een andere positie en automatische rollback zijn niet
  beschikbaar als hersteloplossing.
- Volledige gelijkschakeling met alle FM9-functies, bredere NAM-ondersteuning en
  onafhankelijke tests op MK1 en andere platforms blijven vervolgwerk.

De technische uitsplitsing staat in de
[resterende acceptatiepunten](AFX3-REMAINING-ACCEPTANCE.md).

## Testlog

### Technische controles op 17 oktober 2026

De gecombineerde regressiesuite voor de UX-voorbereiding slaagde met 160 tests.
Een aanvullende run van de verplichte controles en UI-tests slaagde met
58 tests. Deze suites overlappen en zijn geen 218 unieke tests.

De Chrome-workflowtest met gesimuleerde API-antwoorden controleerde onder meer
routekeuze, inputbehoud, focus, schermindeling, reset en afzonderlijke
toestemmingen voor verzenden, NAM-installatie en opslaan. De bijgewerkte live
interface is daarnaast alleen-lezen gecontroleerd; daarbij veranderden geen
presetparameters of NAM-inhoud. Dit is geen nieuwe luistertest.

### Volledige gebruikerstest

Status: nog uit te voeren. De
[UX-testvolgorde](AFX3-UX-USER-TEST.md) staat klaar. Er is nog geen uitslag van
die volledige test geregistreerd.

De aanvullende automatische controles op fouten, kortere desktopvensters,
lange plannen, toetsenbordbediening en documentatie staan in het
[controleverslag](AFX3-UX-PREFLIGHT.md). Deze controles vervangen de
gebruikerstest niet.

Na de laatste UX-correcties slaagt de gecombineerde simulatortest met 203 tests
en de aanvullende verplichte/UI-run met 58 tests. Ook deze suites overlappen.
De uitgebreide Chrome-test slaagt inclusief wegvallende verbinding tijdens
SEND, tekstbehoud en het ontbreken van een automatische nieuwe schrijfpoging.

## Een bevinding melden op GitHub

Maak per probleem één melding en houd bedieningsproblemen en klankfeedback
gescheiden. Gebruik voor nieuwe testresultaten dezelfde velden:

```text
Titel:
Datum:
TC-versie of commit:
Apparaat en uitvoering:
Exacte firmware:
Besturingssysteem:
Preset en scene:
Bouwroute: AMP/CAB of NAM
Categorie: bediening / verzending / opslaan / klank / controller
Stappen om te herhalen:
Verwacht resultaat:
Werkelijk resultaat en exacte foutmelding:
Heeft TC iets verzonden of opgeslagen?:
Screenshot of gecontroleerd diagnoserapport:
Status: nieuw / in onderzoek / opgelost / hertest geslaagd
```

Verwijder API-sleutels, tokens, accountgegevens en onnodige persoonlijke
informatie voordat je iets deelt. Plaats geen volledige privepresetbanken,
NAM-modelbestanden of ruwe protocolopnamen standaard in een openbaar issue.
Aanvullende metingen kunnen via een afgesproken privelocatie worden gedeeld.
