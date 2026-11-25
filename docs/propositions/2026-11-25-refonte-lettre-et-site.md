# Refonte de la lettre et du site : points encore ouverts

Proposition de Claude Projet, 25/11/2026. Branche `projet/references`, partie de
`main` au commit `d608718` (« Docs : une seule session Code à la fois, décision
« pas d'IA » datée »).

Ce document remplace `REFONTE-LETTRE-ET-SITE.md` (23/11/2026, rédigé sur le
commit `544c448`). Il ne garde que les points encore ouverts sur `d608718` et
décrit chaque besoin et sa solution, sans correctif de code. Benchmark :
`2026-11-23-references-medias.md`. Maquettes : canevas Design « Mon député —
maquettes lettre et fiche » (https://claude.ai/artifact/R4hG76ogVyQpVrRp5T7hSa),
artboards `Main.dc.html` (lettre) et `Fiche.dc.html` (fiche).

Conventions : **À VÉRIFIER** = non confirmé ; « Ouvert » = absent de `d608718`
d'après une lecture du code (à confirmer par Claude Code) ; « À décider » =
demande une décision de l'éditeur.

---

## 0. Déjà traité ou écarté (pour mémoire, ne pas reprendre)

- Corrections de la relecture du 23/11/2026 (article 49.3, dédoublonnage des
  titres de dossiers, suppression des étapes avant insertion, mention
  « Dernière étape connue ») : présentes sur `d608718`.
- Présence en commission (cas de la lettre du 03/11–09/11/2026) : pas d'écart.
  L'indicateur compte toutes les réunions où le député figure sur une feuille de
  présence, quelle que soit la commission, comme l'indique la Méthodologie ; la
  lettre affiche la commission de chaque réunion. La commission principale (la
  plus fréquentée sur 90 jours) ne sert qu'aux « Textes de sa commission ».
- Lettre à périodes fixes, ligne de groupe à 60 %, médianes, résumé « En bref »,
  thèmes mis en avant : décidés et réalisés (journal du 23/11/2026).
- Résumés par IA des amendements et des interventions : écartés par l'éditeur le
  23/11/2026 (voir le journal des décisions).

---

## 1. Principes éditoriaux (référence, sans changement de code)

Besoin : que chaque nouvelle rubrique respecte les mêmes règles de neutralité,
en année préélectorale.

Solution : appliquer à toute rubrique future ces règles, inspirées de la charte
publiée par QuiVoteQuoi :

1. La décision avant le scrutin : d'abord ce qui a été décidé, puis la position
   du député.
2. Le sujet avant l'acte : vote, amendement et intervention sur une même mesure
   regroupés.
3. Aucun score global ni jugement ; des nombres plutôt que des adverbes.
4. Tout chiffre mis en contexte (médianes du groupe et de l'Assemblée).
5. Titre = intitulé du texte (ou intitulé en langage courant validé), jamais
   « le groupe X a voté contre » ; tous les groupes dans le même ordre.
6. Toute règle de calcul nouvelle est décrite dans la page Méthodologie.

Ouvert, À VÉRIFIER dans les données : les votes en liberté de vote sont-ils
identifiables ? Le taux moyen de votes conformes à la ligne du groupe (environ
95 % selon Datan) est à recalculer sur nos données avant toute mention.

---

## 2. Lettre

Base : `lettre/contenu.py` (rubriques) et `lettre/visuel.py` (mise en page). Déjà
en place sur `d608718` : « En bref », cartes de « L'essentiel » avec étiquette de
type, barre empilée, majorité requise et pastille de position ; participation
comparée aux médianes ; votes contre le groupe ; ordre du jour ; amendements
regroupés par texte ; contraintes e-mail (tableaux, styles en ligne, repli
au-delà de 90 Ko).

### 2.1 Frise « Où en sont ces textes » — Ouvert

- Besoin : rendre lisible d'un coup d'œil l'étape atteinte par un texte. La
  rubrique est aujourd'hui une liste de phrases.
- Solution : dans la version visuelle, une rangée de pastilles en cellules de
  tableau, une par étape **déjà franchie et datée** (✓ adopté, ✕ rejeté),
  suivie de la phrase actuelle. **Aucune étape future** : la règle « État d'un
  texte » interdit d'en déduire la suite (la maquette du 23/11/2026, avec des
  cercles vides « à venir », est à corriger sur ce point).

### 2.2 Ses votes par thème — Ouvert, À décider

- Besoin : voir d'un bloc ce que le député a voté sur un même texte.
- Solution : un bloc par texte (étiquette de thème, intitulé), une case par vote
  (P / C / A, avec la lettre écrite, pas la couleur seule), décompte, accord avec
  son groupe (n sur N). Limité aux textes de la période ; les thèmes mis en avant
  par l'abonné en premier.
- À décider : rubrique nouvelle ou remplacement d'une partie de « L'essentiel »,
  au regard du poids de la lettre (limite de 90 Ko).

### 2.3 En-tête — Ouvert, mineur

- Besoin : reconnaître le groupe sans lire le sigle.
- Solution : pastille à la couleur officielle du groupe (`organes.couleur`, déjà
  utilisée sur la fiche du site), toujours suivie du nom du groupe.
- Les « trois tuiles de chiffres » de la maquette sont probablement remplacées
  par « En bref » : À décider (les abandonner ou non).

### 2.4 En commission — Ouvert, mineur

- Solution : une case par réunion dotée d'une feuille (présent / absent /
  excusé, avec libellé), au-dessus de la liste actuelle.

### 2.5 Version texte

- Solution : barres en caractères (`████░░`) là où la version visuelle a une
  barre ; pas d'emoji porteur de sens. À VÉRIFIER : état actuel de la version
  texte sur ce point.

---

## 3. Site (fiche d'un député)

Le journal du 24/11/2026 limite la refonte à l'accueil : les autres pages gardent
leur présentation. Les points ci-dessous demandent donc **une décision nouvelle
de l'éditeur** avant toute réalisation. Ils rejoignent le point ouvert « Fiche du
site : maquette visuelle de l'éditeur » de `docs/etat-du-projet.md`. Le site
étant statique et généré en Python, du SVG en ligne suffit, sans JavaScript.

Par priorité proposée :

1. **Hémicycle par vote majeur** : 577 points colorés par position, député
   entouré. `deputes.place_hemicycle` existe ; la correspondance entre ce numéro
   et une géométrie de sièges publiée est À VÉRIFIER. À défaut, points rangés par
   groupe ou par position, avec la mention « points rangés par position, pas par
   siège ».
2. **Parcours d'un texte** : même frise que 2.1, étapes franchies seulement.
3. **Barre fine sous chaque vote** du tableau des votes sur les textes entiers,
   avec résultat et majorité requise.
4. **Ses votes par thème** : barres horizontales par thème de `themes.py`.
5. **Page « Comprendre »** : groupe ≠ parti ; vote de l'Assemblée ≠ loi ;
   pourquoi la participation à tous les scrutins est faible ; parcours de la
   loi. Textes éditoriaux à rédiger et à valider par l'éditeur.
6. **Faits marquants** par député : vote le plus serré auquel il a participé,
   dernier vote contre son groupe, thème le plus voté. Des chiffres, aucune
   appréciation.
7. **Activité dans le temps** : calendrier par semaine, mention « volume, pas
   qualité ».
8. **Images de partage (Open Graph)** par fiche.
9. **Photo officielle** : conditions de réutilisation des photos de l'Assemblée
   À VÉRIFIER avant tout usage.

---

## 4. Charte visuelle

Constat : `lettre/visuel.py` reprend déjà, à quelques nuances près, la charte
proposée le 23/11/2026 (fond crème, texte `#1c1f26`, accent `#1f4e79`, pour
`#2f7d4f`, contre et abstention avec libellé). Proposition : s'en tenir aux
valeurs du code comme référence commune au site et à la lettre ; règles
maintenues — couleur toujours doublée d'un libellé, barres partant de zéro, même
ordre des groupes, police système, ni dégradé ni emoji.

---

## 5. Données relevées le 23/11/2026 (pour tests)

Relevées pendant l'exploration ; à relire dans la base avant de servir de
valeurs attendues. Le scrutin n° 8430 a déjà été repris par Claude Code.

- Lettre de Marie-Charlotte Garin (EcoS, Rhône 3e), 03/11–09/11/2026 : 8
  scrutins sur 215 ; vote solennel du 04/11 sur la première partie du PLF 2027
  (rejetée) ; présente à 1 des 4 réunions avec feuille.
- Rejet de la première partie du PLF 2027 (04/11/2026) : 458 contre et 2
  abstentions selon la presse ; voix pour À VÉRIFIER dans le scrutin officiel.
- Scrutin n° 8431 (21/07/2026, PPL réseaux sociaux et mineurs, texte de CMP) :
  279 pour, 81 contre, 66 abstentions selon Datan, À VÉRIFIER dans la base.

---

## 6. Hors périmètre ou à décider plus tard

- Réseaux sociaux (Instagram 4:5, carrousel hebdomadaire) : non prioritaire ;
  voir les règles de QuiVoteQuoi dans le benchmark.
- Synthèses par « politique » à la manière de TheyWorkForYou : choix éditorial
  risqué ; méthode à publier avant toute mise en œuvre.
