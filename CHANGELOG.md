# Changelog

## v0.1.5

- Protocole « 3D upgrade » (Denon 6.0.2) de l'AVP-A1HD, vérifié sur l'ampli réel :
  - Dynamic EQ / Dynamic Volume deviennent un seul sélecteur `PSDYN` :
    Off / Dynamic EQ / Dynamic EQ + Volume (les anciennes commandes `PSDYNEQ` / `PSDYNVOL`
    n'existaient pas). Le réglage Day / Evening / Midnight (`PSDYNSET`) est inchangé.
  - Ajout d'Audyssey DSX (Off / Height / Wide, largeur et hauteur de scène), du niveau de
    référence Dynamic EQ (0 / 5 / 10 / 15 dB) et de Dolby PLIIz Height (marche/arrêt, gain).
  - Retrait du mode Night, supprimé par la mise à jour de l'ampli.
- Page « Audyssey » de la télécommande refaite en conséquence.

## v0.1.4

- Le widget du lecteur multimédia affiche l'état de l'ampli : source (ligne titre),
  mode surround (ligne artiste) et volume en dB, avec « Muted » si coupé (ligne album).
  Lignes vidées en veille.

## v0.1.3

- Identifiant d'appareil stable (`denon`), indépendant de l'adresse IP de la passerelle.
  Changer d'IP (simulateur → Dock 3) ne renomme plus les entités et ne casse plus les
  activités ni les pages qui les utilisent. Les entités d'une configuration existante
  sont renommées une dernière fois au passage à cette version.

## v0.1.0

- Première version : Denon AVP-A1HD en RS-232 via passerelle TCP (Dock 3, IP2SL…).
- Couche `denon_control` indépendante : transport TCP avec framing CR, parser typé, modèle d'état.
- Media player, Remote (4 pages UI, 151 commandes simples, pass-through brut), 15 selects, 11 switches, 13 sensors.
- Reconnexion automatique, polling de sécurité 30 s, rafraîchissement après allumage.
- Simulateur de Denon et 47 tests (parser rejouant une capture réelle, bout-en-bout).
- Port TCP par défaut 5000 (port externe 2 du Dock 3 ; le port 1 émet des messages de démarrage).
- Documentation du câblage : le Dock 3 intègre un transceiver RS-232, un simple cordon jack/DB9 croisé suffit.
