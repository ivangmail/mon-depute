/* Formulaire d'abonnement à la lettre d'un député. */
(function () {
  'use strict';
  var formulaire = document.getElementById('abonnement');
  if (!formulaire) return;
  var retour = document.getElementById('abonnement-retour');
  formulaire.addEventListener('submit', function (evenement) {
    evenement.preventDefault();
    var champs = {};
    new FormData(formulaire).forEach(function (valeur, cle) { champs[cle] = valeur; });
    var bouton = formulaire.querySelector('button');
    bouton.disabled = true;
    retour.className = 'doux';
    retour.textContent = 'Envoi en cours…';
    fetch(formulaire.action, { method: 'POST', headers: { 'Content-Type': 'application/json' },
                               body: JSON.stringify(champs) })
      .then(function (r) { return r.json().then(function (j) { return { ok: r.ok, json: j }; }); })
      .then(function (reponse) {
        retour.className = 'alerte';
        retour.textContent = reponse.json.message || reponse.json.erreur ||
          'Une erreur est survenue. Réessayez plus tard.';
        if (reponse.ok) formulaire.reset();
      })
      .catch(function () {
        retour.className = 'alerte';
        retour.textContent = 'Le service d’abonnement ne répond pas. Réessayez plus tard.';
      })
      .then(function () { bouton.disabled = false; });
  });
})();
