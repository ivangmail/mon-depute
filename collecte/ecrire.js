/* Rédaction d'un message au député, envoyé par la messagerie du visiteur.

   Rien ne passe par le site : la page prépare seulement des liens vers la
   messagerie choisie, ou copie le message dans le presse-papiers. */
(function () {
  'use strict';
  var bloc = document.getElementById('courrier');
  if (!bloc) return;
  var adresse = bloc.dataset.adresse;
  var objet = document.getElementById('courrier-objet');
  var texte = document.getElementById('courrier-texte');
  var retour = document.getElementById('courrier-retour');
  var e = encodeURIComponent;

  function lien(id, url) {
    var a = document.getElementById(id);
    if (a) a.href = url;
  }

  // Les adresses des messageries web doivent rester identiques à celles de liens_envoi() (fiche.py).
  function actualiser() {
    var o = objet.value, t = texte.value;
    lien('envoi-gmail', 'https://mail.google.com/mail/?view=cm&fs=1&tf=cm&to=' + e(adresse) +
      '&su=' + e(o) + '&body=' + e(t));
    lien('envoi-outlook', 'https://outlook.live.com/mail/0/deeplink/compose?to=' + e(adresse) +
      '&subject=' + e(o) + '&body=' + e(t));
    lien('envoi-yahoo', 'https://compose.mail.yahoo.com/?to=' + e(adresse) +
      '&subject=' + e(o) + '&body=' + e(t));
    lien('envoi-defaut', 'mailto:' + adresse + '?subject=' + e(o) + '&body=' + e(t));
  }
  objet.addEventListener('input', actualiser);
  texte.addEventListener('input', actualiser);

  // « L'interroger sur ce vote » : le message est préparé dans le bloc, à compléter.
  [].forEach.call(document.querySelectorAll('a.interroger'), function (a) {
    a.addEventListener('click', function (evenement) {
      evenement.preventDefault();
      objet.value = a.dataset.objet;
      texte.value = a.dataset.texte;
      actualiser();
      retour.textContent = 'Le message a été préparé à partir de ce vote. Complétez-le, puis choisissez comment l’envoyer.';
      bloc.scrollIntoView({ block: 'start' });
      texte.focus();
    });
  });

  document.getElementById('copier').addEventListener('click', function () {
    var complet = 'À : ' + adresse + '\nObjet : ' + objet.value + '\n\n' + texte.value;
    function echec() {
      texte.focus();
      texte.select();
      retour.textContent = 'La copie automatique n’a pas fonctionné : le message est sélectionné, copiez-le avec Ctrl+C, puis écrivez à ' + adresse + '.';
    }
    if (!navigator.clipboard) { echec(); return; }
    navigator.clipboard.writeText(complet).then(function () {
      retour.textContent = 'Message copié, avec l’adresse et l’objet : collez-le dans votre messagerie.';
    }, echec);
  });

  actualiser();
})();
