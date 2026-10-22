# TC FX3 gebruikerstest voor de publicatie

De eigenaar test de begrijpelijkheid van de workflow nadat de aansluiting op de
oorspronkelijke TC-interface is gecontroleerd. De MK1-NAM-test staat afzonderlijk
in [de vervolgopdracht](AFX3-MK1-NAM-TEST.md) en hoort niet bij deze sessie.
Publicatiepunten 4, 5 en 6 volgen pas na deze gebruikerstest.

## Voorbereiding

Gebruik de ene onderhouden TC op http://127.0.0.1:8909/ en sluit Axe-Edit voor
MIDI-gebruik door TC. Controleer apparaat, MK2-keuze, firmware en doelpreset.
Behoud 326 en 328 als referenties; kies bijvoorbeeld 323 alleen als de inhoud
daarvan mag worden vervangen. Bewaar eigen niet-opgeslagen wijzigingen eerst.
De technische zero-test in werkgeheugen 322 is geen muzikale referentie.

Laat externe audio gedempt tijdens scene-, preset- en bouwhandelingen. De
interface is geen fysieke volumebegrenzer. Luister pas na een geslaagde bouw
op laag fysiek volume. NAM-installatie en presetopslag zijn aparte toestemmingen.

## Testvolgorde

1. Begin met NEW DESIGN. Annuleer eenmaal om te controleren dat bestaande tekst
   blijft staan; bevestig daarna het nieuwe ontwerp. De Fractal mag hierdoor
   niet veranderen.
2. Schrijf een verzoek zonder audiolink. Controleer dat Enter een nieuwe regel
   maakt en dat de primaire knop de volgende stap duidelijk aangeeft.
   Als TC EVEN AFSTEMMEN toont, beantwoord dan de concrete vraag en gebruik
   VERDER MET MIJN ANTWOORDEN. Een uitgesteld onderdeel mag niet alsnog als
   uitgevoerd of gegarandeerd in het voorstel staan.
   Bij TONECOMMAND HEEFT EEN VRAAG vul je het lege antwoordveld in en klik je
   VERSTUUR ANTWOORD. Test dat Enter alleen een nieuwe regel maakt en dat je
   antwoord in DESIGN CONVERSATION terugkomt. Een vervolgvraag moet aansluiten
   op wat je al hebt verteld.
3. Laat TC de routes onderzoeken. Kies zelf AMP/CAB of NAM als TC daarom vraagt.
   Er mag nog niets op de Fractal of in NAM-geheugen worden geschreven.
4. Controleer het gewenste sceneaantal in de ontwerpopties en maak het voorstel.
   Klap het verzoek in en uit: de volledige tekst moet behouden blijven.
5. Doorloop PLAN, REVIEW en CONFIRM. Controleer doelpreset, scenenamen, modellen,
   wijzigingen en gedeelde kanalen. Teruggaan of tekst veranderen mag geen oude
   verzendtoestemming behouden.
6. Verzend alleen het bedoelde voorstel na doelcontrole en bevestigde externe
   demping. Wacht op het resultaat. Een fout of gedeeltelijke verzending is geen
   reden om dezelfde opdracht automatisch opnieuw te versturen.
7. Luister op laag volume naar de scenes. Noteer apart wat onduidelijk was in
   de bediening en wat beter moet klinken.
8. Gebruik BIJSTUREN NA LUISTERTEST voor een gerichte aanpassing van gekozen
   scenes. Controleer weer het voorstel voordat je verzendt.
9. Probeer een nieuw ontwerp met een audiolink direct in de verzoektekst.
   Gebruik dezelfde stappen. Metingen zijn geen bewijs van gitaarisolatie of
   exacte klankreproductie.
10. Test opslaan alleen als de build goed is en het doel mag worden overschreven.
    PREVIEW STORE is nog geen opslag; de aparte bevestiging maakt die permanent.

## Technische voorbereiding op 17 oktober 2026

De request-flow gebruikt de gedeelde upstream-vormgeving. GENERATE PLAN begint
waar nodig met routeonderzoek; CHOOSE ROUTE opent daarna de expliciete keuze.
De ontwerpopties beginnen ingeklapt en tonen het huidige sceneaantal in de kop.
De extra FX3-bibliotheken blijven rechts uitklapbaar. Enter blijft een nieuwe
regel. Firmware-, review-, dempings-, SEND- en Store-controles blijven behouden.

De Chrome-workflowtest met gesimuleerde API-antwoorden slaagt, inclusief
routekeuze zonder automatische planbouw, inputbehoud, focus, layout op drie
desktopbreedtes en afzonderlijke NAM-installatie- en Store-toestemmingen.
De gecombineerde regressiesuite slaagt met 160 tests. Dit vervangt de
gebruikerstest of een nieuwe hardware- en luistertest niet.

De aanvullende vier controles staan in het
[UX-controleverslag](AFX3-UX-PREFLIGHT.md). Bij een netwerkfout of ongeldig
antwoord verschijnt een apart meldingsvak. Gebruik RESCAN voor een nieuwe
statuscontrole; verstuur een onbekend schrijfresultaat niet automatisch opnieuw.

## Voorbeeldverzoek

Maak een preset met de naam Metallica albums, met een AMP/CAB-oplossing en acht
scenes. Maak voor Kill 'Em All, Ride the Lightning, Master of Puppets en ...And
Justice for All telkens een ritmescene en een soloscene. Geef elk album een
herkenbaar ander klankdoel en maak het verschil tussen ritme en solo duidelijk.
Kies beschikbare versterkers en passende cabs; gebruik geschikte Usercabs als
die in de actuele bibliotheek staan. Voeg alleen nuttige effecten toe. Verander
geen globale pedaaltoewijzingen. Maak eerst een voorstel; sla nog niets op.

Controleer dat TC acht scenes uit het verzoek overneemt. Je kunt bewust een
ander aantal kiezen in ONTWERPOPTIES. Een beperktere route mag de vraag om acht
scenes niet zonder jouw keuze reduceren.

## Feedback om te bewaren

Noteer per probleem de stap, wat je verwachtte, wat er gebeurde en een screenshot
met de statusmelding. Vermeld TC-versie, presetnummer en scene. Deel geen sleutels
of accountgegevens. Houd UX-feedback gescheiden van klankfeedback, zodat beide
gericht kunnen worden opgelost voordat punten 4, 5 en 6 beginnen.

Gebruik de vaste meldingsvelden in het
[gebruikerslog voor GitHub](AFX3-GEBRUIKERSLOG.md). De status van de volledige
gebruikerstest blijft open totdat de bevindingen zijn vastgelegd.
