# Journal de bord — épisode 2 : la fiabilité, et la sortie de Genesis

> ⚠️ **DIRECTIVE DE RESTRUCTURATION (ai-01 GO, msg 2026-08-14T171023-yw6rzx) :**
> ce contenu sera **intégré par EXTENSION de `journal-de-bord.md`** (pas de second
> fichier). Les sections ci-dessous deviennent les nouveaux chapitres insérés
> **AVANT le chapitre 7 « Ce que ça enseigne »** actuel ; la section « leçons » de
> ce draft devient la **réécriture du chapitre conclusion** (absorbe juillet–août).
> L'ordre narratif imposé est respecté ci-dessous : 3 modes de panne un à un
> (watchdog v2→v5) → cause matérielle (boot-OOM, gpu-util qui ment) → 2 faux
> coupables (autoheal, phantom mount) → résolution (sortie de Genesis).
> **Chaque chiffre doit citer sa trace réelle** (NOTES.md phase 1/2, memory
> project_*.md, docker logs horodatés) — provenance dans le body de la PR.
> Tracker : **CoursIA #10977** (fille de #4427).
>
> DRAFT (vllm-side) — récit FR-first. Mêmes garde-fous : aucun secret, endpoints
> génériques, sources créditées, chiffres vérifiés.
>
> **Statut rédaction :** COMPLETE (sections 1–7, 2026-08-19). Prochaine étape :
> assemblage worktree (chapitres insérés avant le chap. 7 existant, conclusion
> §7 ci-dessus = réécriture du sien) + PR atomique. Cron 576b491c.

---

## 1. Où nous étions restés

Fin juin, le serveur tournait sur la configuration promue en mai : modèle MoE
Qwen3.6-35B-A3B quantifié AWQ, cache KV TurboQuant via l'arbre de patches
downstream Genesis, deux GPU en tensor parallelism, près de deux millions de
tokens de cache, fenêtre de contexte 262 K. Le journal s'arrêtait sur une
formule : *servir un LLM en production, c'est entretenir un compromis vivant*.

Juillet et août ont donné à cette formule son contenu le plus concret. Pendant
huit semaines, le sujet n'a plus été d'optimiser le compromis — débit, contexte,
VRAM — mais de tenir le service : des pannes qui ne ressemblaient à rien de
connu, des redémarrages qu'on s'infligeait soi-même sans le savoir, et un
détective story en trois actes qui a fini par renverser la décision
architecturale de mai. La configuration d'aujourd'hui n'est plus Genesis : c'est
du vLLM d'origine, version publiée, sans patch tree. Ce second journal raconte
comment on en est arrivé là.

## 2. Le moteur qui répondait… sauf quand il générait

Le premier incident sérieux arrive début juillet. Le point d'entrée HTTP répond
parfaitement — 200, rapide — mais les générations s'arrêtent net. Les requêtes
restent ouvertes, aucun token ne sort, aucun message d'erreur nulle part. La
couche API est vivante ; le moteur de décodage, lui, est figé. Nous appellerons
ce mode de panne un *wedge* : le moteur coincé derrière une API souriante.

La leçon architecturale de ce premier wedge est double. D'abord, **« le service
répond » ne prouve rien** : un simple *health check* HTTP ne distingue pas un
moteur en bonne santé d'un moteur figé. Ensuite, la panne ne se guérit pas
seule : il faut la détecter vite et redémarrer vite.

Le premier watchdog naît de là — un petit sidecar conteneurisé qui sonde
régulièrement le service. Sa version 2 introduit le geste décisif : quand la
santé HTTP est bonne, il envoie une **vraie requête de génération de 24
tokens**. Deux timeouts consécutifs pendant que la santé HTTP dit 200 : c'est un
wedge, on redémarre. Le temps de réaction passe d'un quart d'heure à deux
minutes. C'est la première itération d'un outil qui en connaîtra cinq : chaque
version existera parce qu'un incident réel a exposé l'angle mort de la
précédente.

Un détail de conception mérite d'être noté, car il reviendra : le watchdog
distingue **boot patient** et **panne** en interrogeant l'état Docker du
conteneur. Un moteur LLM de cette taille met six à quinze minutes à démarrer
(chargement des poids, compilation, capture des CUDA graphs). Pendant ce temps,
toutes les sondes échouent — et c'est normal. Redémarrer pendant le boot serait
le pire geste possible. Toute la difficulté de la surveillance, on va
l'apprendre pendant des semaines, tient dans cette phrase : *savoir ce qui est
une panne et ce qui est une lenteur légitime.*

## 3. La carte graphique partagée avec le bureau

Mi-juillet, un deuxième ennemi se révèle : la panne qui arrive **au
démarrage**, pas en service. Trois fois en dix-neuf jours, le moteur boucle sur
des crashes d'allocation mémoire CUDA au boot — `out of memory` — alors même
que la carte affiche des gigaoctets libres.

L'explication tient en une phrase peu intuitive : **le budget mémoire déclaré
n'est pas la mémoire réellement consommée.** vLLM réserve un pourcentage de la
VRAM (le paramètre *gpu-memory-utilization*), mais plusieurs mécanismes vivaient
**en dehors** de ce budget : allocations temporaires des noyaux MoE Marlin,
pools de pré-allocation du patch tree, et les CUDA graphs. Mesuré sur la carte
sans bureau : +2,1 à +2,8 Gio au-dessus du budget nominal. La carte maudite est
la numéro 0 — partagée avec le bureau Windows (explorateur, éditeur, navigateur)
dont la consommation VRAM fluctue. Un pic du bureau entre deux phases
d'initialisation du moteur suffit à faire déborder le vrai budget, et le crash
n'indique jamais que quelques dizaines de méga-octets manquent — avec des Gio
« libres » affichés : c'est le plafond du pool, pas l'épuisement physique.

La réponse opérationnelle est une descente prudente : 0,82 → 0,78 → 0,70. Chaque
palier est déployé, mesuré, documenté. Le coût, cumulé : la capacité de cache KV
passe d'environ deux millions de tokens à 1,24 million (−38 %) — mais
l'occupation observée en production est de 2 à 7 %, et la fenêtre reste couverte
presque cinq fois. La leçon : **quand un budget
ment, on ne corrige pas le symptôme, on remesure le budget** — puis on accepte
un coût explicite plutôt qu'une panne récurrente.

Ce cycle de pannes apporte aussi sa version de watchdog : la v4 apprend à lire
le compteur de redémarrages de Docker *pendant* la phase de boot. Une boucle de
crash au démarrage re-entre indéfiniment dans l'état « starting » — ce que le
watchdog traitait comme un boot patient à attendre. La v4 fait la différence
entre les deux : un boot sain garde le compteur plat, une boucle de crash le
fait grimper. Après trois incréments, le watchdog crie au crash-loop — il ne
redémarre pas (Docker le fait déjà, inutilement), il **signale**. Détection,
pas action : là aussi, un principe qui tiendra.

## 4. La nuit des deux fausses pistes

Le 6 août, une panne de réelle gravité — une heure d'indisponibilité — se
révèle à l'analyse être **deux incidents distincts**, dont un seul était
compris.

Le premier est banal dans son déclenchement, pas dans son effet : un défaut de
passage GPU force l'arrêt de la couche WSL (le sous-système Linux de l'hôte
Windows qui porte les données). Au redémarrage de la pile, le montage du cache
de poids — qui vit dans WSL et est monté dans le conteneur Docker — résout sur
un **dossier vide**. Comportement de Docker : quand la source d'un bind mount
est momentanément injoignable (WSL pas encore prêt), le moteur substitue un
répertoire vide plutôt que d'échouer. Le moteur démarre alors « normalement »
et entreprend de **re-télécharger les 19 Go du modèle** — à vitesse nulle, le
chemin réseau étant le même que celui qui est cassé.

Ce qui rend ce piège redoutable, c'est sa signature : **tous les indicateurs
disent « boot patient »**. Conteneur démarré, santé « starting », compteur de
redémarrages plat, logs arrêtés juste après « chargement du modèle ». Pendant
une heure, l'outil de surveillance et l'opérateur ont regardé un téléchargement
fantôme en croyant surveiller un démarrage. Le discriminant tient en une
commande : mesurer la taille du répertoire de cache dans le conteneur — 47 Go
attendus, quelques centaines de méga-octets trouvés. Depuis, ce test fait partie
du rituel post-reboot.

Deux correctifs en sortent. D'abord le montage durci : une syntaxe Docker qui
**échoue bruyamment** si la source est manquante, au lieu de créer un répertoire
vide. Ensuite le watchdog v5 : un mode de détection dédié au boot-stall —
compteur plat, santé « starting » depuis trop longtemps, et jamais la ligne
« modèle chargé » dans les logs. Il ne redémarre pas (redémarrer remonterait le
même dossier vide) : il **affiche le diagnostic et la commande de réparation**.

La même nuit, après réparation, le watchdog v5 est mis à l'épreuve pour de bon :
un vrai wedge, celui-là — décodage effondré de 90 à 0 tokens/s au milieu d'une
génération, déclenché par une requête minuscule (19 Ko — pas le profil
gros-contexte des incidents précédents), ni manque mémoire, ni pagination, ni
la moindre trace d'erreur. Le HTTP reste vivant pendant tout le gel. Le
watchdog le détecte, redémarre, l'ingénierie tient : environ onze minutes
d'indisponibilité au lieu d'une dérive silencieuse. La v5 apporte aussi la
grâce de chauffe post-boot : un moteur fraîchement démarré répond lentement à
ses premières générations (mesuré : 52 s, puis 16 s, puis 0,5 s) alors que sa
santé HTTP dit déjà 200 — la v4 comptait ces lenteurs comme des débuts de
wedge et avait redémarré un moteur **en parfaite santé**. La v5 ne compte
jamais les trois premières sondes après un boot.

## 5. Le redémarrueur invisible

Août apporte sa part de découvertes forensiques. La plus importante tient en un
détail d'exploitation : sur cette machine tourne un petit conteneur utilitaire
venu d'un autre stack — un « auto-heal » chargé de relancer les conteneurs dont
le healthcheck échoue. Sa configuration dit *tous les conteneurs*. Il n'a jamais
été pensé pour le moteur LLM ; *tous* ne fait pas de tri. Chaque fois que Docker
marquait notre moteur `unhealthy`, ce gardien bienveillant le redémarrait — en
concurrence directe de notre watchdog, dont toute la conception repose sur l'idée
opposée : ne jamais interrompre un boot, même lent, même en échec apparent.

Sa signature est ce qui l'a rendu invisible pendant des mois. Un redémarrage
qu'il provoque laisse **code de sortie zéro**, pas d'OOM, et surtout — c'est le
détail qui tue — **un compteur de redémarrages inchangé** : un `docker restart`
manuel n'incrémente pas le compteur que la restart-policy incrémente. Or toute
notre détection de boucles de crash lit ce compteur. Elle était structurellement
aveugle à ce gardien. La seule trace côté moteur était un `KeyboardInterrupt`
anodin dans l'initialisation.

Le déclic vient en voulant comprendre pourquoi le premier démarrage à froid de
la nouvelle image mourait systématiquement à dix-sept minutes : le boot à froid
dépassait la période de grâce du healthcheck, le gardien le tuait — et
l'examen de ses logs a révélé qu'il avait aussi frappé **pendant l'incident du
10 août**, au milieu de la fenêtre qu'on analysait depuis des heures. Une partie
des redémarrages de cet incident venait de lui : l'analyse elle-même devait être
révisée. Le correctif tient en une ligne — un label qui dit au gardien « pas
celui-ci » — mais la leçon dépasse ce cas : **avant d'analyser un redémarrage
inexpliqué, dresser la liste des autorités de redémarrage présentes sur
l'hôte.** Un compteur de redémarrages stable ne prouve pas qu'aucun
redémarrage n'a eu lieu.

La même quinzaine offre un second avertissement du même genre, dans l'autre
sens : pendant une expérience de validation sur la troisième carte, l'outil
standard de supervision GPU de l'hôte rapportait **152 Mo occupés** — pendant
que le conteneur d'essai y servait un modèle à des milliers de tokens par
seconde. L'outil regardait la carte ; la charge vivait dans un espace qu'il ne
comptait pas. Le garde-fou anti-collision bâti sur cette lecture ne protégeait
donc de rien, et l'accord explicite entre équipes est resté la seule barrière
fiable. Deux fois le même enseignement, sous deux formes : **un indicateur
silencieux vaut exactement ce que vaut la liste de ce qu'il ne mesure pas** —
et cette liste, seul l'examen manuel la révèle.

## 6. La sortie de Genesis — deux phases et une preuve

Restait la question qui pendait depuis mai : l'arbre de patches downstream qui
nous sauvait du crash TurboQuant — en étions-nous encore prisonniers ? Deux
raisons de vouloir en sortir. D'abord la reproductibilité : les images nightly
sur lesquelles l'arbre se construit sont purgées au bout de quelques jours, et
l'image de production était devenue impossible à reconstruire — elle n'existait
plus qu'en une copie locale, sauvegardée. Ensuite, upstream avait repris le
travail sur la famille de bugs qui nous avait fait fuir : quatre correctifs
étaient passés, vérifiés présents dans la version publiée.

La méthode d'août tient en deux phases, chacune ne testant qu'une chose à la
fois. **Phase 1, de jour, sur la carte d'expérimentation** : un petit modèle
proxy, un contexte réduit, la question unique « le crash se reproduit-il sur le
vLLM d'origine ? ». Réponse : non — et une donnée annexe précieuse, un premier
appel de compilation à froid du décodeur quantifié mesuré à **328 secondes**,
retombant à 4 une fois le cache chaud. **Phase 2, de nuit, sur le vrai moteur**
: bascule de la production elle-même, le 10 août à 23 h 45 UTC, batterie de
treize tests.

La nuit faillit mal tourner pour de mauvaises raisons : le premier démarrage
fut tué par le redémarrueur invisible du chapitre précédent (c'est cette nuit-là
qu'il fut identifié), puis la première batterie afficha des échecs inquiétants
sur les longs contextes — qui se révélèrent être un module de hachage absent de
l'image d'origine, importé trop paresseusement pour se signaler avant l'usage.
Deux corrections mineures, et la batterie repassa **13 sur 13**.

Puis la preuve, celle qui légitimait tout le reste : un pré-remplissage **chunké
de 253 503 tokens** — l'équivalent du plus gros contexte que la fenêtre autorise,
celui qui avait tué le moteur en mai — passa **en 58,6 secondes**, suivi d'une
requête de survie. Le crash historique ne se reproduisait pas. Deux autres gains
mesurés tombèrent avec : la carte partagée avec le bureau regagnait **1,8 Gio**
de marge (les pools de pré-allocation du patch tree vivaient hors budget), et le
coût de la sortie — 17 % de capacité de cache — s'avérait sans effet pratique,
l'occupation en production plafonnant à quelques pourcents.

Restait le débit, et c'est là que l'épisode livre sa leçon de méthode la plus
nette. La première mesure sembla désastreuse : 37 % sous la référence
documentée. Conclusion hâtive : le vLLM d'origine serait plus lent. Mais la
référence datait de **mai**, sur une machine dont l'état avait changé. La seule
comparaison honnête est un A/B **la même nuit**, même machine, mêmes scripts —
Genesis redéployé, mesures refaites, retour au stock. Verdict inversé : le vLLM
d'origine gagnait de 14 % en charge multi-utilisateurs et de 29 % en
mono-flux. Et la vraie découverte était ailleurs : **les deux piles étaient
ensemble ~45 % sous les chiffres de mai**. Ce n'était ni l'un ni l'autre —
c'était la machine qui avait perdu du débit, pour une cause non élucidée à ce
jour (horloges, pilote, plan d'alimentation, charge du bureau), ouverte en
chantier distinct. La migration était justifiée par la comparaison de cette
nuit-là ; les chiffres de mai cessèrent d'être des références.

## 7. Ce que ça enseigne (conclusion réécrite, absorbant juillet–août)

Si l'on ne devait retenir que quelques idées de ce journal :

1. **Quatre grandeurs en tension.** Débit, contexte, qualité, VRAM. On choisit, on ne maximise pas tout. Le bon choix dépend du *workload réel*, pas d'un benchmark abstrait. Juillet–août en a ajouté une cinquième, invisible jusqu'ici : **la disponibilité** — qu'un compromis tienne huit semaines sans interruption vaut parfois plus qu'un dixième de débit supplémentaire.
2. **Le matériel décide du possible — et il ment parfois.** Sur du grand public Ada, la VRAM et la génération de GPU ferment des portes avant même la question de la vitesse ; et le budget mémoire déclaré n'est pas la mémoire consommée. Quand un indicateur (budget, compteur, sonde) se tait sur une partie du réel, seul l'examen manuel de ce qu'il ne mesure pas le révèle.
3. **Mesurer, toujours — et dater la mesure.** Grid search, benchmarks, soaks : chaque décision majeure s'appuie sur un chiffre reproductible. La saga d'août a ajouté le corollaire : une référence vieillit avec la machine qui l'a produite. La seule comparaison honnête est un A/B **même nuit**, même matériel, mêmes scripts. Comparer une mesure du jour à une mesure de trois mois plus tôt a failli faire rejeter une migration qui gagnait en réalité de 14 %.
4. **Un silence n'est pas une santé.** Un HTTP 200 ne prouve pas que le décodage vit ; un compteur de redémarrages plat ne prouve pas que rien n'a redémarré ; un indicateur GPU à sa baseline ne prouve pas qu'une carte est libre. Chaque mode de panne découvert ce trimestre était *silencieux* — la panoplie de surveillance existe précisément parce qu'aucun indicateur unique n'est honnête.
5. **Détecter et agir sont deux métiers différents.** Le watchdog a appris, version après version, à ne pas confondre lenteur légitime et panne : ne jamais redémarrer pendant un boot, offrir une grâce de chauffe, distinguer la boucle de crash (redémarrer ne sert à rien) du montage fantôme (redémarrer aggrave). La moitié de l'ingénierie de fiabilité consiste à *ne pas faire* la chose réflexe.
6. **Documenter les échecs — et les faux coupables.** Le cimetière des modèles rejetés, les impasses de décodage spéculatif, mais aussi les deux faux coupables d'août : le redémarrueur invisible et le téléchargement fantôme. Une analyse d'incident révisée après coup vaut autant qu'une analyse juste du premier coup : elle enseigne la même prudence méthodique.
7. **`vérifié` ≠ `supposé`.** Avant de déclarer une cause, un test qui la force. Avant de propager un fait, une vérification. La règle de juin a payé tout l'été.
8. **La reproductibilité est une propriété de production.** L'image irréconstructible a fini par peser plus lourd que les correctifs qu'elle portait : un artefact qu'on ne peut pas reconstruire est une dette, pas un actif. Sortir de l'arbre de patches pour une version publiée — en vérifiant, preuve à l'appui, que la raison d'être de l'arbre avait disparu — a rendu le service reconstruisable du jour au lendemain. Amont *et* aval, toujours, mais l'amont d'abord quand il rattrape son retard.

Le serveur qui tourne aujourd'hui — modèle MoE Qwen3.6-35B-A3B sur un vLLM d'origine versionné, cache TurboQuant, plus d'un million de tokens de contexte, fenêtre de 262 K, vision et raisonnement, surveillé par un watchdog qui a appris la patience — n'est pas un point d'arrivée. C'est l'état courant d'un arbitrage qui a déjà changé dix fois et changera encore. Les deux mois que racontent ces chapitres n'ont presque rien optimisé : ils ont *tenu* le service, compris pourquoi il tombait, et remboursé la dette de reproductibilité contractée en mai. C'est aussi ça, servir un LLM en production : non pas trouver *la* configuration, mais entretenir un compromis vivant, mesuré, surveillé et honnêtement documenté.

---

*Sources (à compléter à la finalisation) : documentation interne de déploiement
(juillet–août 2026), journaux d'itération phase 1/2, mémoires de projet. Issues
amont vLLM citées : #41726. Patches Genesis : Sandermage, v7.72.x.*
