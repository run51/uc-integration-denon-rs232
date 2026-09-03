# Changelog

## v0.1.0

- Première version : Denon AVP-A1HD en RS-232 via passerelle TCP (Dock 3, IP2SL…).
- Couche `denon_control` indépendante : transport TCP avec framing CR, parser typé, modèle d'état.
- Media player, Remote (4 pages UI, 151 commandes simples, pass-through brut), 15 selects, 11 switches, 13 sensors.
- Reconnexion automatique, polling de sécurité 30 s, rafraîchissement après allumage.
- Simulateur de Denon et 47 tests (parser rejouant une capture réelle, bout-en-bout).
- Port TCP par défaut 5000 (port externe 2 du Dock 3 ; le port 1 émet des messages de démarrage).
- Documentation du câblage : le Dock 3 intègre un transceiver RS-232, un simple cordon jack/DB9 croisé suffit.
