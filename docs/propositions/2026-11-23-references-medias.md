# Références : médias, sites et comptes étudiés pour la lettre et le site « Mon député »

Document de référence rédigé le 23/11/2026. Compagnon de `2026-11-25-refonte-lettre-et-site.md` (anciennement `REFONTE-LETTRE-ET-SITE.md`).

**Méthode de consultation** (indiquée pour chaque entrée) :
- **Navigateur** : page ou compte vu directement dans Chrome, captures à l'appui, le 23/11/2026.
- **Page lue** : contenu récupéré par lecture automatique de la page (texte, pas de rendu visuel).
- **Recherche** : connu seulement par des résultats de recherche ou des sources secondaires ; à confirmer.

Les descriptions sont des paraphrases ; ce document ne reproduit pas le contenu des sources.

---

## 1. Synthèse

| Constat | Conséquence pour Mon député |
|---|---|
| Le répertoire visuel est restreint et constant : barre ou hémicycle pour/contre/abstention, position des groupes dans un ordre fixe, étiquettes de statut, grands chiffres, un bloc par information. | Reprendre ce vocabulaire, que les lecteurs connaissent déjà. |
| Sur les réseaux, le ressort principal n'est pas le graphique mais la **phrase-titre** avec le verbe du résultat mis en valeur, une **étiquette** de catégorie et des **pictogrammes**. | Phrase-titre + étiquette dans chaque carte de vote. |
| Vert = pour, rouge = contre, jaune = abstention chez Datan, monparlement et sur le site actuel. | Garder la convention, toujours avec un libellé. |
| Aucun site étudié ne montre le **parcours d'un texte** de façon visuelle, alors que l'Assemblée en fait un contenu pédagogique. | Frise des étapes : élément différenciant. |
| Un e-mail n'affiche ni SVG, ni iframe, ni JavaScript de façon fiable. | Graphiques en cellules de tableau dans la lettre ; SVG réservé au site. |
| Les indicateurs d'activité bruts ont été vivement contestés par des députés (cas NosDéputés). | Toujours contextualiser, ne jamais classer ni noter. |

---

## 2. Sites de suivi parlementaire

### Datan — https://datan.fr
- **Consultation** : navigateur (page du scrutin n° 8431) + pages lues (votes décryptés, statistiques, FAQ).
- **Éléments visuels** : bandeau ADOPTÉ/REJETÉ ; bande de couleur pour / abstention / contre en tête du vote ; graphique en anneau ; logos des groupes rangés dans deux cadres « Pour » et « Contre » ; carte de l'auteur du texte avec photo ; tableau des groupes (vote, pour, abstention, contre, participation, cohésion) ; boutons de partage ; fenêtre d'appel au don.
- **Contenu** : « votes décryptés » choisis pour leur écho médiatique ou les divisions qu'ils révèlent, reformulés et classés en 14 catégories ; trois taux de participation (votes solennels, textes de la commission du député, tous les votes) ; taux de loyauté et de proximité ; lettre mensuelle.
- **À retenir** : la triple mesure de participation (déjà reprise dans le code) ; l'étiquette de résultat ; la phrase de synthèse en pourcentages.
- **À éviter** : les logos de groupes (lourds, peu lisibles en petit) ; la fenêtre surgissante.

### monparlement.fr — https://www.monparlement.fr
- **Consultation** : navigateur (page d'accueil, deux écrans) + page lue.
- **Éléments visuels** : hémicycle en points colorés (pour, contre, abstention, sans vote) pour le dernier vote majeur, avec décompte et étiquette « Adopté » ; cartes de vote avec barre fine pour/contre et décompte des groupes ; « sismographe » des votes ayant divisé chaque groupe (un trait par vote, hauteur = intensité du désaccord) ; cartes de records en très grands chiffres avec barre ; un point par motion de censure ; recherche « votre député » par code postal ; bascule de thème clair/sombre ; flux RSS.
- **À retenir** : la référence visuelle la plus aboutie du benchmark ; l'hémicycle en points ; les cartes à barre fine ; les grands chiffres sobres.
- **Remarque** : une première lecture automatique de la page n'avait pas détecté l'hémicycle ; l'observation dans le navigateur l'a corrigée.

### Eutyn — https://eutyn.fr
- **Consultation** : page lue.
- **Éléments** : profil du député en chiffres clés (participation, part de votes pour et contre, amendements, commissions) ; résultat global de chaque scrutin ; cohésion du groupe.
- **À retenir** : les tuiles de chiffres clés. Pas de lettre d'information mentionnée.

### MonÉlu — https://mon-elu.vercel.app
- **Consultation** : page lue.
- **Éléments** : votes, présence et désaccords avec le groupe ; résumés en langage clair rédigés par IA et signalés comme tels ; vérification d'affirmations (vrai, faux, trompeur, invérifiable) ; quiz de proximité ; ordre du jour ; API publique. Pas de lettre d'information.
- **À retenir** : la transparence sur l'usage de l'IA ; l'ordre du jour à venir.
- **Réserve** : le site déclare lui-même une accessibilité non conforme ; incohérence relevée entre 577 et 655 députés affichés.

### NosDéputés.fr (Regards Citoyens) — https://www.nosdeputes.fr
- **Consultation** : recherche uniquement (site non accessible depuis l'environnement de travail).
- **Éléments** : indicateurs d'activité (semaines d'activité, interventions, présence en commission), graphiques individuels, nuages de mots-clés, alertes e-mail.
- **Analyse** : site pionnier (2009), longtemps en quasi-monopole sur les indicateurs d'activité ; vivement critiqué par des députés et un ministre pour son effet sur les comportements ; l'association avait envisagé de compter des mots plutôt que des interventions.
- **À retenir** : le risque de réputation des classements ; d'où la règle « contextualiser, ne jamais noter ».

### QuiVoteQuoi — https://github.com/pierrebelin/QuiVoteQuoi (ticket n° 83)
- **Consultation** : page lue (ticket « Instagram : post quotidien et carrousel hebdomadaire »).
- **Règles publiées** : formats 4:5 et Reel/Story, une image par scrutin ; scrutin du jour = celui qui a réuni le plus de votants (critère publié) ; tous les groupes, toujours dans le même ordre ; titre = intitulé du texte, jamais une formule sur un groupe ; des nombres, pas d'adverbes ; source et lien sur chaque chiffre ; explications pédagogiques les jours sans séance (groupe ≠ parti, vote sur l'ensemble ≠ loi adoptée, votes à main levée absents des données) ; test de relecture par une personne de droite et une de gauche ; relecture manuelle avant toute publication.
- **À retenir** : la meilleure charte de neutralité trouvée ; directement transposable à la lettre.

### TheyWorkForYou (mySociety, Royaume-Uni) — https://www.theyworkforyou.com
- **Consultation** : recherche (pages « voting summaries » de plusieurs députés) ; page de méthodologie non accessible.
- **Éléments** : votes regroupés par domaine politique, résumés en formules graduées (« a voté de façon constante pour… »), décompte pour/contre/absences et période, comparaison avec les députés comparables du parti, score d'alignement, mention des votes libres.
- **À retenir** : le regroupement thématique avec comparaison au parti.
- **Réserve** : les « politiques » sont définies à la main ; choix éditorial risqué à transposer.

### abgeordnetenwatch (Allemagne) — https://www.abgeordnetenwatch.de
- **Consultation** : recherche (exemples de lettres et de pages de votes).
- **Éléments** : la lettre contient une rubrique sur quelques votes importants montrant comment les députés ont voté ; sur les profils, une liste de votes avec des étiquettes simples (pour, contre, non participé) ; pages de vote avec décomptes ; questions publiques aux élus.
- **À retenir** : l'étiquette par vote plutôt que des décomptes ; quelques votes choisis dans la lettre.

### GovTrack et ProPublica (États-Unis)
- **Consultation** : recherche.
- **Éléments** : votes manqués comparés à une médiane (GovTrack) ; base des explications d'absence et des votes serrés manqués (ProPublica).
- **À retenir** : la comparaison à une médiane ; l'idée de signaler les absences sur des votes serrés.

### Scruti — https://scruti.fr
- **Consultation** : non consulté (site inaccessible) ; cité par une analyse tierce comme proposant des alertes par élu, groupe, texte ou thème.
- **Statut** : **À VÉRIFIER**.

---

## 3. Sources institutionnelles et médias

### Assemblée nationale — site https://www.assemblee-nationale.fr
- **Consultation** : pages lues (scrutins, positions de vote, fiche « Les votes à l'Assemblée nationale »).
- **Éléments** : page de scrutin avec diagramme du résultat, synthèse (votants, exprimés, majorité absolue) et répartition par groupe ; mises au point de vote ; données ouvertes (https://data.assemblee-nationale.fr).
- **À retenir** : la source primaire de tout chiffre ; l'ordre de référence des groupes.

### Assemblée nationale — Instagram @assembleenationale
- **Consultation** : navigateur (profil, un reel, un carrousel), 23/11/2026.
- **Observé** :
  - reel sur le projet de loi relatif à la résilience des infrastructures critiques et à la cybersécurité : texte en surimpression où le verbe « a adopté » est surligné en vert, précision « en première lecture » ; la légende indique que le texte, adopté dans des termes différents de ceux du Sénat, poursuit sa navette ;
  - carrousel épinglé « Quel est le parcours de la loi ? » : vignettes sur fond papier, pictogrammes en aplat bleu (pupitre, hémicycle, table de commission, mains levées), une idée par vignette, mots-clés en gras ;
  - autres formats : titres en capitales blanches sur photo, sujets patrimoniaux.
- **À retenir** : la phrase-titre avec verbe surligné ; la mention de la navette ; le style des pictogrammes pour la page « Comprendre ».

### LCP — Assemblée nationale
- **Site** https://lcp.fr — page lue : articles « Qu'a voté votre député ? » avec infographies Flourish et recherche par nom, circonscription ou groupe ; bilans du vote des groupes sur les projets de loi.
- **Instagram @lcp_an** — navigateur : surtout des vidéos ; portrait, surtitre d'émission, titre en capitales sur bandeau.
- **X @LCP** — navigateur (sans connexion, affichage limité) : messages à puces emoji, affiches d'émission avec photos.
- **À retenir** : le titre « Qu'a voté votre député ? » comme accroche ; le reste est peu transposable à une lettre.

### HugoDécrypte — Instagram @hugodecrypte
- **Consultation** : navigateur (profil), 23/11/2026 ; environ 5,8 millions d'abonnés affichés.
- **Observé** : photo plein cadre, étiquette colorée en haut (« DERNIÈRE MINUTE », « EN FINALE ! »), phrase-résumé en blanc avec mots-clés en gras, logo en coin.
- **À retenir** : une étiquette de catégorie par information (dans la lettre : VOTE SOLENNEL, VOTE SERRÉ, CONTRE SON GROUPE).

### Hugo au Perchoir — TikTok @hugo.au.perchoir
- **Consultation** : navigateur (profil), 23/11/2026.
- **Observé** : vidéos face caméra issues d'une chaîne Twitch de vulgarisation parlementaire ; certaines vignettes reprennent l'écran de résultat de l'hémicycle (votants, exprimés, majorité absolue, pour, contre).
- **À retenir** : afficher la **majorité requise**, qui rend un vote serré compréhensible d'un coup d'œil.

### Mediapart (graphique Datawrapper) — https://datawrapper.dwcdn.net/Ggka2/5
- **Consultation** : recherche.
- **Éléments** : analyse en composantes principales des votes de chaque député, en nuage de points.
- **Analyse** : trop complexe pour une lettre ; éventuellement pour une page d'analyse du site.

### Presse utilisée pour les faits
- **Moneyvox** — rejet de la première partie du PLF 2027 le 04/11/2026 (458 contre, 2 abstentions selon l'article) : recherche.
- **LCP** — même vote, réactions des groupes : recherche.
- **IFRAP** — « Principaux amendements au budget 2026 : qui a voté quoi ? », exemple de présentation par mesure : recherche.
- **Le Monde (Décodeurs)** — un article sur les mesures du budget 2026 cité par une autre IA n'a pas été retrouvé : **À VÉRIFIER**.

---

## 4. Références de format et de technique

### Axios — méthode « Smart Brevity »
- **Consultation** : recherche (guides Axios HQ, presse spécialisée).
- **Principes** : « quoi de neuf » puis « pourquoi c'est important » ; paragraphes courts, gras, puces ; chaque information tient sur un écran ; Axios cite une recherche selon laquelle une majorité de lecteurs survole les longs textes ; objets d'e-mail d'environ six mots.
- **Analyse** : utile pour la densité de la lettre ; critiqué pour l'usage mécanique des puces.

### Contraintes des clients e-mail
- **SVG** : non fiable (Gmail jamais entièrement, Outlook abandonné fin 2025 ; Apple Mail et Thunderbird l'affichent) — sources : Buttondown, caniemail.com.
- **Iframes** : non prises en charge par les lettres et flux RSS ; Datawrapper propose des images PNG de repli publiées automatiquement.
- **Graphiques en tableau** : barres en cellules colorées, sans image ni SVG, compatibles avec tous les clients et le mode sombre — source : emailmd.
- **Poids** : Gmail coupe les messages de plus de 102 Ko (« Afficher l'intégralité du message ») — sources : MxToolbox, HubSpot, beehiiv.
- **Bonnes pratiques** : mise en page en tableaux, styles en ligne, largeur 600–640 px, texte alternatif, boutons en HTML — sources : WooCommerce, Omnisend, SitePoint.

### Graphiques parlementaires
- **Hémicycle (« parliament chart »)** : un point par siège, en demi-cercle ; modèles Flourish et bibliothèques diverses ; popularisé par Wikipédia — source : Flourish, visualizing.org.

### API Anthropic (si résumés IA)
- **Message Batches** : environ 50 % de réduction, traitement sous 24 heures, compatible avec le cache de prompt ; cache d'une heure recommandé pour les lots (documentation Anthropic, extrait). Le cumul exact des réductions sur les jetons en cache diffère selon les sources secondaires : **À VÉRIFIER** sur https://docs.claude.com.

---

## 5. Limites de ce benchmark

- Les comptes X n'ont été vus que sans connexion (affichage limité) ; le compte X de Datan essayé renvoie une erreur 404.
- Les publications vues sur Instagram et TikTok sont un échantillon (profils et deux publications ouvertes), pas un relevé exhaustif.
- Plusieurs sites (TheyWorkForYou, NosDéputés, Scruti) n'étaient pas accessibles directement ; leurs descriptions reposent sur des résultats de recherche.
- Les droits de réutilisation des photos officielles de l'Assemblée n'ont pas été vérifiés.
