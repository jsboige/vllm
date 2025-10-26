# Rapport de Performance Qwen3

Date: 2025-05-27 02:39:25

## Résumé des performances

| Modèle | Latence moyenne (ms) | Débit moyen (tokens/s) | Utilisation mémoire |
|--------|----------------------|------------------------|--------------------|
| micro (Qwen/Qwen3-1.7B-FP8) | 1652.79 | 87.01 | 97.8% |
| mini (Qwen/Qwen3-8B-AWQ) | 2442.17 | 54.38 | 74.1% |
| medium (Qwen/Qwen3-32B-AWQ) | 2771.85 | 44.36 | 76.7% |

## Détails pour micro (Qwen/Qwen3-1.7B-FP8)

### Connectivité

- **Statut**: OK
- **Temps de réponse**: 5.5ms
- **Nombre de modèles**: 1

### Performances

- **Temps de réponse moyen**: 1652.79ms
- **Temps de réponse min**: 546.25ms
- **Temps de réponse max**: 4545.87ms
- **Débit moyen**: 87.01 tokens/s
- **Débit min**: 11.0 tokens/s
- **Débit max**: 97.53 tokens/s

### Résultats par type de prompt

#### Salutation simple

- **Temps de réponse moyen**: 1890.9ms
- **Débit moyen**: 62.9 tokens/s

**Exemple de réponse**:

```

Okay, the user greeted me in French with "Bonjour, comment allez-vous?" which means "Hello, how are you?" I need to respond in one sentence. Since the user is using French, I should acknowledge their greeting in French
```

#### Question factuelle

- **Temps de réponse moyen**: 1072.6ms
- **Débit moyen**: 93.2 tokens/s

**Exemple de réponse**:

```

Okay, the user is asking two questions: the capital of France and when the Eiffel Tower was built. Let me start with the capital. I know that France's capital is Paris. That's pretty straightforward. But wait, I should double-check to make sure there's no confusion with other cities. Paris is the political, cultural, and economic center, so that's correct.

Now, the Eiffel Tower. I remember it's a famous landmark in Paris. But when
```

#### Génération de code

- **Temps de réponse moyen**: 1562.8ms
- **Débit moyen**: 96.0 tokens/s

**Exemple de réponse**:

```

Okay, I need to write a Python function to calculate the factorial of a number. Let me think about how to approach this. 

First, what's a factorial? The factorial of a number n, denoted as n!, is the product of all positive integers up to n. So 5! is 5 × 4 × 3 × 2 × 1 = 120. And 0! is defined as 1. 

Now, how to implement this in Python. The function should take an integer as input and return its factorial. Let's start with the basics. 

I remember that recursion is a common way to do this, but for small numbers, it's manageable. However, recursion can
```

#### Raisonnement logique

- **Temps de réponse moyen**: 2084.8ms
- **Débit moyen**: 95.9 tokens/s

**Exemple de réponse**:

```

Okay, let's see. The problem is: A train leaves Paris at 8 AM and travels at 200 km/h towards Marseille, which is 800 km away. What time does it arrive?

Hmm, so I need to figure out the travel time and then add that to the departure time. The distance is 800 km, and the speed is 200 km/h. 

First, time is equal to distance divided by speed. So, time = 800 km / 200 km/h. Let me calculate that. 800 divided by 200 is 4. So, the travel time is 4 hours.

Now, the train leaves at 8 AM. If it takes 4 hours, then adding 4 hours to 8 AM should give the arrival time. Let's do that. 8 AM plus 4 hours is 12 PM, which is noon.

Wait
```


## Détails pour mini (Qwen/Qwen3-8B-AWQ)

### Connectivité

- **Statut**: OK
- **Temps de réponse**: 2.3ms
- **Nombre de modèles**: 1

### Performances

- **Temps de réponse moyen**: 2442.17ms
- **Temps de réponse min**: 858.53ms
- **Temps de réponse max**: 4469.71ms
- **Débit moyen**: 54.38 tokens/s
- **Débit min**: 11.19 tokens/s
- **Débit max**: 59.02 tokens/s

### Résultats par type de prompt

#### Salutation simple

- **Temps de réponse moyen**: 2067.2ms
- **Débit moyen**: 42.2 tokens/s

**Exemple de réponse**:

```

Okay, the user greeted me in French with "Bonjour, comment allez-vous?" which means "Hello, how are you?" They want a response in one sentence. I need to answer in French.

First, I should acknowledge their greeting
```

#### Question factuelle

- **Temps de réponse moyen**: 1715.5ms
- **Débit moyen**: 58.3 tokens/s

**Exemple de réponse**:

```

Okay, the user is asking two questions here. First, they want to know the capital of France. That's pretty straightforward. I know the capital is Paris, but I should make sure there's no confusion with other cities like Lyon or Marseille. Wait, no, Paris is definitely the capital. Maybe they just want confirmation.

Then the second part is about when the Eiffel Tower was built. I remember it was constructed in the late 19th century. Let me think
```

#### Génération de code

- **Temps de réponse moyen**: 2557.2ms
- **Débit moyen**: 58.7 tokens/s

**Exemple de réponse**:

```

Okay, I need to write a Python function that calculates the factorial of a number. Let me think about how to approach this. 

First, what's a factorial? The factorial of a number n, denoted as n!, is the product of all positive integers up to n. So, 5! is 5*4*3*2*1 = 120. But wait, what about zero? Oh right, 0! is 1. So the function should handle that case.

Now, how to implement this in Python. There are a few ways. Maybe using a loop? Like starting from 1 and multiplying up to n. Or maybe recursion? But recursion might not be the best for large
```

#### Raisonnement logique

- **Temps de réponse moyen**: 3428.9ms
- **Débit moyen**: 58.3 tokens/s

**Exemple de réponse**:

```

Okay, so I need to figure out when a train leaves Paris at 8:00 AM and travels at 200 km/h to Marseille, which is 800 km away. Let me start by recalling some basic concepts. 

First, I know that to find the time it takes for a train to travel a certain distance, I can use the formula: time = distance / speed. That makes sense because if the train is moving at a constant speed, dividing the total distance by the speed should give me the time it takes. 

So the distance here is 800 km, and the speed is 200 km/h. Let me write that down: time = 800 km / 200 km/h. Hmm, dividing 800 by 200... that should be 4 hours. Wait, is that right? Let me check. 200 km/h means the train covers 2
```


## Détails pour medium (Qwen/Qwen3-32B-AWQ)

### Connectivité

- **Statut**: OK
- **Temps de réponse**: 2.4ms
- **Nombre de modèles**: 1

### Performances

- **Temps de réponse moyen**: 2771.85ms
- **Temps de réponse min**: 1167.2ms
- **Temps de réponse max**: 4383.75ms
- **Débit moyen**: 44.36 tokens/s
- **Débit min**: 36.47 tokens/s
- **Débit max**: 46.16 tokens/s

### Résultats par type de prompt

#### Salutation simple

- **Temps de réponse moyen**: 1237.0ms
- **Débit moyen**: 40.6 tokens/s

**Exemple de réponse**:

```

Okay, the user started with a greeting in French: "Bonjour, comment allez-vous? Répondez en une phrase." So they're asking how I'm doing and want a response in one sentence. I need to make sure I
```

#### Question factuelle

- **Temps de réponse moyen**: 2214.3ms
- **Débit moyen**: 45.2 tokens/s

**Exemple de réponse**:

```

Okay, the user is asking for the capital of France and when the Eiffel Tower was built. Let me start by confirming the capital. I know that Paris is the capital, but I should double-check in case there's any recent change, though I don't think so. Next, the Eiffel Tower's construction dates. I remember it was built for the 1889 World's Fair, but I need to be precise. The actual start and completion years are
```

#### Génération de code

- **Temps de réponse moyen**: 3281.8ms
- **Débit moyen**: 45.7 tokens/s

**Exemple de réponse**:

```

Okay, I need to write a Python function to calculate the factorial of a number. Let me think about how to approach this. 

First, what's a factorial? Oh right, the factorial of a number n is the product of all positive integers up to n. Like 5! is 5*4*3*2*1 = 120. And 0! is defined as 1. So I have to handle that case too.

So the function should take an integer as input and return the factorial. Let's start with the basic structure. Maybe a function called factorial that takes a parameter n. 

Now, how to compute it. The straightforward way is to multiply from 1 to n. For
```

#### Raisonnement logique

- **Temps de réponse moyen**: 4354.3ms
- **Débit moyen**: 45.9 tokens/s

**Exemple de réponse**:

```

Okay, let's see. The problem is about a train leaving Paris at 8 AM heading to Marseille, which is 800 km away, and it's traveling at 200 km/h. I need to figure out what time it arrives. Hmm, so first, I should probably calculate the time it takes for the train to cover the 800 km distance at 200 km/h. 

Alright, time is distance divided by speed. So, time = 800 km / 200 km/h. Let me do that division. 800 divided by 200 is 4. So that would be 4 hours of travel time. If the train leaves at 8 AM, adding 4 hours would mean it arrives at 12 PM. Wait, but 8 AM plus 4 hours is 12 PM, right? Let me check again. Starting at 8, adding 4
```


## Méthodologie

- **Nombre d'itérations par test**: 3
- **Types de prompts testés**:
  - Salutation simple: "Bonjour, comment allez-vous? Répondez en une phrase."
  - Question factuelle: "Quelle est la capitale de la France et quand la Tour Eiffel a-t-elle été construite?"
  - Génération de code: "Écrivez une fonction Python qui calcule la factorielle d'un nombre."
  - Raisonnement logique: "Si un train part de Paris à 8h et roule à 200 km/h vers Marseille qui est à 800 km, à quelle heure arrive-t-il?"

- **Métriques mesurées**:
  - Latence (temps de réponse en ms)
  - Débit (tokens générés par seconde)
  - Utilisation mémoire GPU
  - Qualité des réponses (exemples fournis)
