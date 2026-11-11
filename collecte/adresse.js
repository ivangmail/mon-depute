/* Recherche du député à partir d'une adresse postale.

   Tout se passe dans le navigateur : l'adresse saisie est envoyée au service
   public de géocodage de l'IGN, qui renvoie ses coordonnées ; la circonscription
   est ensuite trouvée ici même, en cherchant dans quel contour tombe le point.
   Le site ne reçoit ni l'adresse ni les coordonnées. */
(function () {
  'use strict';
  var GEOCODAGE = 'https://data.geopf.fr/geocodage/search';
  var COMMUNES = 'https://geo.api.gouv.fr/communes';
  var PART_MINIMALE = 0.03;  // part de la commune en dessous de laquelle on ignore une circonscription
  var MARGE = 100;        // mètres : en dessous, on signale la proximité d'une limite
  var RATTRAPAGE = 300;   // mètres : point hors de tout contour, mais tout près d'un

  function departement(codeCommune) {
    codeCommune = String(codeCommune || '');
    return /^9[78]/.test(codeCommune) ? codeCommune.slice(0, 3) : codeCommune.slice(0, 2);
  }

  // Un anneau est une liste à plat [lon, lat, lon, lat, ...].
  function dansAnneau(lon, lat, a) {
    var dedans = false;
    for (var i = 0, j = a.length - 2; i < a.length; j = i, i += 2) {
      var xi = a[i], yi = a[i + 1], xj = a[j], yj = a[j + 1];
      if ((yi > lat) !== (yj > lat) && lon < (xj - xi) * (lat - yi) / (yj - yi) + xi) {
        dedans = !dedans;
      }
    }
    return dedans;
  }

  // Un polygone est [contour, trou, trou, ...].
  function dansPolygones(lon, lat, polygones) {
    return polygones.some(function (p) {
      if (!dansAnneau(lon, lat, p[0])) return false;
      for (var t = 1; t < p.length; t++) if (dansAnneau(lon, lat, p[t])) return false;
      return true;
    });
  }

  // Distance en mètres du point au bord le plus proche des polygones.
  function distanceAuBord(lon, lat, polygones) {
    var kx = 111320 * Math.cos(lat * Math.PI / 180), ky = 110540, mini = Infinity;
    polygones.forEach(function (p) {
      p.forEach(function (a) {
        for (var i = 0, j = a.length - 2; i < a.length; j = i, i += 2) {
          var x1 = (a[j] - lon) * kx, y1 = (a[j + 1] - lat) * ky;
          var x2 = (a[i] - lon) * kx, y2 = (a[i + 1] - lat) * ky;
          var dx = x2 - x1, dy = y2 - y1, l2 = dx * dx + dy * dy;
          var t = l2 ? Math.max(0, Math.min(1, -(x1 * dx + y1 * dy) / l2)) : 0;
          var d = Math.hypot(x1 + t * dx, y1 + t * dy);
          if (d < mini) mini = d;
        }
      });
    });
    return mini;
  }

  /* Renvoie { numero, certain, distance, voisine } ou null.
     certain : le point est dans un contour, à plus de MARGE mètres du bord.
     voisine : numéro de l'autre circonscription la plus proche, si elle est à
     moins de MARGE mètres. */
  function trouver(lon, lat, circos) {
    var numeros = Object.keys(circos), dedans = null, proches = [];
    numeros.forEach(function (n) {
      var g = circos[n].g;
      if (dedans === null && dansPolygones(lon, lat, g)) dedans = n;
      proches.push({ numero: n, distance: distanceAuBord(lon, lat, g) });
    });
    proches.sort(function (a, b) { return a.distance - b.distance; });
    if (dedans !== null) {
      var bord = proches.filter(function (p) { return p.numero === dedans; })[0].distance;
      var autre = proches.filter(function (p) { return p.numero !== dedans; })[0];
      var voisine = autre && autre.distance < MARGE ? autre.numero : null;
      return { numero: dedans, certain: bord >= MARGE || !voisine, distance: bord, voisine: voisine };
    }
    if (proches.length && proches[0].distance < RATTRAPAGE) {
      var second = proches[1] && proches[1].distance < RATTRAPAGE ? proches[1].numero : null;
      return { numero: proches[0].numero, certain: false, distance: proches[0].distance, voisine: second };
    }
    return null;
  }

  // Contour GeoJSON (Polygon ou MultiPolygon) -> polygones à anneaux à plat.
  function aplatir(geometrie) {
    var polygones = geometrie.type === 'MultiPolygon' ? geometrie.coordinates : [geometrie.coordinates];
    return polygones.map(function (p) {
      return p.map(function (anneau) {
        var plat = [];
        anneau.forEach(function (c) { plat.push(c[0], c[1]); });
        return plat;
      });
    });
  }

  /* Circonscriptions qui couvrent une commune, de la plus grande part à la plus
     petite. On sème une grille de points dans la commune et on regarde dans
     quelle circonscription tombe chacun : les imprécisions de tracé le long
     d'une limite ne pèsent alors presque rien et sont écartées. */
  function circosDeCommune(contour, circos) {
    var commune = aplatir(contour), x0 = Infinity, x1 = -Infinity, y0 = Infinity, y1 = -Infinity;
    commune.forEach(function (p) {
      for (var i = 0; i < p[0].length; i += 2) {
        x0 = Math.min(x0, p[0][i]); x1 = Math.max(x1, p[0][i]);
        y0 = Math.min(y0, p[0][i + 1]); y1 = Math.max(y1, p[0][i + 1]);
      }
    });
    var N = 40, compte = {}, total = 0, numeros = Object.keys(circos);
    for (var i = 0; i < N; i++) for (var j = 0; j < N; j++) {
      var x = x0 + (x1 - x0) * (i + 0.5) / N, y = y0 + (y1 - y0) * (j + 0.5) / N;
      if (!dansPolygones(x, y, commune)) continue;
      total++;
      for (var k = 0; k < numeros.length; k++) {
        if (dansPolygones(x, y, circos[numeros[k]].g)) {
          compte[numeros[k]] = (compte[numeros[k]] || 0) + 1; break;
        }
      }
    }
    return Object.keys(compte).map(function (n) { return { numero: n, part: compte[n] / total }; })
      .filter(function (c) { return c.part >= PART_MINIMALE; })
      .sort(function (a, b) { return b.part - a.part; });
  }

  window.MonDepute = { departement: departement, dansPolygones: dansPolygones,
                       distanceAuBord: distanceAuBord, trouver: trouver,
                       circosDeCommune: circosDeCommune };

  var champ = document.getElementById('adresse');
  if (!champ) return;
  var liste = document.getElementById('suggestions');
  var resultat = document.getElementById('resultat');
  var minuteur = null, enCours = null;

  function element(nom, texte, attributs) {
    var e = document.createElement(nom);
    if (texte) e.textContent = texte;
    Object.keys(attributs || {}).forEach(function (k) { e.setAttribute(k, attributs[k]); });
    return e;
  }
  function vider(e) { while (e.firstChild) e.removeChild(e.firstChild); }
  function message(texte, classe) {
    vider(resultat);
    resultat.appendChild(element('p', texte, { class: classe || 'doux' }));
  }
  function ordinal(n) { return n === '1' ? '1re' : n + 'e'; }

  // Repli : filtre la liste des députés affichée plus bas sur la page.
  function filtrerListe(texte) {
    var q = document.getElementById('q');
    if (!q) return;
    q.value = texte;
    q.dispatchEvent(new Event('input'));
    q.scrollIntoView({ block: 'center' });
  }

  function ligneDepute(circo, numero, nomDepartement) {
    var p = element('p');
    if (circo.depute) {
      var a = element('a', circo.depute.nom, { href: circo.depute.lien });
      var b = element('b'); b.appendChild(a); p.appendChild(b);
      p.appendChild(document.createTextNode(' (' + circo.depute.groupe + ') · '));
    } else {
      p.appendChild(element('b', 'Siège actuellement vacant'));
      p.appendChild(document.createTextNode(' · '));
    }
    p.appendChild(document.createTextNode(
      ordinal(numero) + ' circonscription, ' + nomDepartement));
    return p;
  }

  function afficher(trouve, donnees, libelle) {
    vider(resultat);
    var circo = donnees.circos[trouve.numero];
    resultat.appendChild(element('p', (trouve.certain ? 'Votre député pour ' :
      'Député le plus probable pour ') + libelle + ' :', { class: 'doux petit' }));
    resultat.appendChild(ligneDepute(circo, trouve.numero, donnees.nom));
    if (!trouve.certain) {
      resultat.appendChild(element('p',
        'Cette adresse se trouve à environ ' + Math.max(1, Math.round(trouve.distance)) +
        ' m de la limite de la circonscription. Les contours utilisés sont simplifiés : ' +
        'le résultat peut être faux à cette distance. Vérifiez le numéro de circonscription ' +
        'sur votre carte électorale.', { class: 'alerte petit' }));
      if (trouve.voisine && donnees.circos[trouve.voisine]) {
        resultat.appendChild(element('p', 'Circonscription voisine :', { class: 'doux petit' }));
        resultat.appendChild(ligneDepute(donnees.circos[trouve.voisine], trouve.voisine, donnees.nom));
      }
    }
  }

  // Résultat établi à partir de la commune seule (sans adresse exacte).
  function afficherCommune(commune, enPanne) {
    var code = departement(commune.code);
    message('Recherche des circonscriptions de ' + commune.nom + '…');
    fetch('circos/' + code + '.json').then(function (r) {
      if (!r.ok) throw new Error('sans contour');
      return r.json();
    }).then(function (donnees) {
      var trouvees = commune.contour ? circosDeCommune(commune.contour, donnees.circos) : [];
      if (!trouvees.length) {
        message('Impossible de situer ' + commune.nom + ' dans une circonscription. ' +
                'La liste ci-dessous est filtrée sur le département.');
        filtrerListe(donnees.nom); return;
      }
      vider(resultat);
      resultat.appendChild(element('p', trouvees.length === 1 ?
        'D’après votre commune (' + commune.nom + '), votre député est :' :
        commune.nom + ' s’étend sur ' + trouvees.length +
        ' circonscriptions. Votre député est l’un de ceux-ci :', { class: 'doux petit' }));
      trouvees.forEach(function (t) {
        resultat.appendChild(ligneDepute(donnees.circos[t.numero], t.numero, donnees.nom));
      });
      var note = 'Ce résultat est établi à partir de la commune, pas de votre adresse exacte.';
      if (enPanne) note += ' Le service d’adresses de l’IGN, qui permet d’être précis, ne répond ' +
        'pas pour le moment : réessayez plus tard.';
      if (trouvees.length > 1) note += ' Le numéro de votre circonscription figure sur votre carte électorale.';
      resultat.appendChild(element('p', note, { class: 'alerte petit' }));
    }).catch(function () {
      message('Les contours des circonscriptions ne sont pas disponibles pour ce territoire. ' +
              'La liste ci-dessous est filtrée sur le département.');
      filtrerListe((commune.departement && commune.departement.nom) || code);
    });
  }

  /* Secours quand le service d'adresses ne répond pas : le code postal donne
     la ou les communes, grâce à l'API publique du découpage administratif. */
  function secours(q) {
    var cp = q.match(/\b\d{5}\b/);
    if (!cp) {
      message('Le service d’adresses de l’IGN ne répond pas pour le moment. Ajoutez votre code ' +
              'postal à l’adresse pour une recherche par commune, ou utilisez la recherche par ' +
              'nom ou par département ci-dessous.');
      return;
    }
    fetch(COMMUNES + '?codePostal=' + cp[0] + '&type=arrondissement-municipal,commune-actuelle' +
          '&fields=nom,code,departement,contour')
      .then(function (r) { if (!r.ok) throw new Error(r.status); return r.json(); })
      .then(function (communes) {
        // Paris, Lyon, Marseille : on garde l'arrondissement, pas la ville entière.
        var arrondissements = communes.filter(function (c) { return /Arrondissement/.test(c.nom); });
        if (arrondissements.length) communes = arrondissements;
        vider(liste);
        if (!communes.length) { message('Aucune commune ne correspond au code postal ' + cp[0] + '.'); return; }
        if (communes.length === 1) { afficherCommune(communes[0], true); return; }
        message('Le service d’adresses de l’IGN ne répond pas pour le moment. ' +
                'Choisissez votre commune :');
        communes.sort(function (a, b) { return a.nom.localeCompare(b.nom, 'fr'); });
        communes.forEach(function (c) {
          var li = element('li'), b = element('button', c.nom + ' (' + cp[0] + ')', { type: 'button' });
          b.addEventListener('click', function () { vider(liste); afficherCommune(c, true); });
          li.appendChild(b); liste.appendChild(li);
        });
      })
      .catch(function () {
        message('Ni le service d’adresses de l’IGN ni celui des communes ne répondent pour le ' +
                'moment. Utilisez la recherche par nom ou par département ci-dessous.');
      });
  }

  function choisir(f) {
    vider(liste);
    champ.value = f.properties.label;
    // Une commune sans rue ni numéro : son centre ne dit rien de la circonscription
    // quand la commune en compte plusieurs. On passe par le contour de la commune.
    if (f.properties.type === 'municipality') {
      message('Recherche de la commune…');
      fetch(COMMUNES + '/' + f.properties.citycode + '?fields=nom,code,departement,contour')
        .then(function (r) { if (!r.ok) throw new Error(r.status); return r.json(); })
        .then(function (c) { afficherCommune(c, false); })
        .catch(function () {
          message('Précisez une rue et un numéro pour trouver votre circonscription.');
        });
      return;
    }
    var lon = f.geometry.coordinates[0], lat = f.geometry.coordinates[1];
    var code = departement(f.properties.citycode);
    var nomDep = String(f.properties.context || '').split(',')[1];
    nomDep = nomDep ? nomDep.trim() : '';
    message('Recherche de la circonscription…');
    fetch('circos/' + code + '.json').then(function (r) {
      if (!r.ok) throw new Error('sans contour');
      return r.json();
    }).then(function (donnees) {
      var trouve = trouver(lon, lat, donnees.circos);
      if (trouve) { afficher(trouve, donnees, f.properties.label); return; }
      message('Cette adresse ne tombe dans aucun contour de circonscription connu. ' +
              'La liste ci-dessous est filtrée sur le département.');
      filtrerListe(donnees.nom);
    }).catch(function () {
      message('Les contours des circonscriptions ne sont pas disponibles pour ce territoire. ' +
              'La liste ci-dessous est filtrée sur le département.');
      filtrerListe(nomDep || code);
    });
  }

  function suggerer() {
    var q = champ.value.trim();
    if (enCours) enCours.abort();
    if (q.length < 4) { vider(liste); return; }
    enCours = new AbortController();
    fetch(GEOCODAGE + '?limit=5&autocomplete=1&q=' + encodeURIComponent(q), { signal: enCours.signal })
      .then(function (r) { if (!r.ok) throw new Error(r.status); return r.json(); })
      .then(function (json) {
        vider(liste);
        var features = (json.features || []).filter(function (f) {
          return f.geometry && f.properties && f.properties.citycode;
        });
        if (!features.length) { message('Aucune adresse trouvée.'); return; }
        vider(resultat);
        features.forEach(function (f) {
          var li = element('li'), b = element('button', f.properties.label, { type: 'button' });
          b.addEventListener('click', function () { choisir(f); });
          li.appendChild(b); liste.appendChild(li);
        });
      })
      .catch(function (e) {
        if (e.name === 'AbortError') return;
        vider(liste);
        secours(q);
      });
  }

  champ.addEventListener('input', function () {
    clearTimeout(minuteur);
    minuteur = setTimeout(suggerer, 250);
  });
  var etranger = document.getElementById('etranger');
  if (etranger) etranger.addEventListener('click', function () {
    filtrerListe('Français établis hors de France');
  });
})();
