import {VideoScriptSchema, type CameraMotion, type VideoScript} from './schema.js';

export type ScriptProvider = 'heuristic' | 'groq' | 'gemini';

export type GenerateScriptOptions = {
  provider?: ScriptProvider;
  groqApiKey?: string;
  geminiApiKey?: string;
};

const CAMERA_MOTIONS: readonly CameraMotion[] = [
  'static',
  'pan_slow',
  'shake_impact',
];

const cleanTopic = (topic: string): string => {
  const normalized = topic.replace(/\s+/g, ' ').trim();
  return normalized.length > 0
    ? normalized
    : 'Tres curiosidades sorprendentes que puedes contar hoy';
};

const durationFor = (text: string): number => {
  const words = text.split(/\s+/).length;
  return Math.max(3, Math.round((words / 2.7) * 10) / 10);
};

export const generateHeuristicScript = (topic: string): VideoScript => {
  const subject = cleanTopic(topic);
  const text = [
    `Detente un segundo: hoy vas a descubrir ${subject.toLowerCase()}.`,
    `Primero, identifica el dato o error que casi todos ignoran. Entenderlo cambia por completo el resultado.`,
    `Después, aplica una acción sencilla y comprueba la diferencia. Guarda este video para recordarlo.`,
  ];
  const prompts = [
    `${subject}, vertical cinematic opening, dramatic lighting, high contrast, no text`,
    `${subject}, detailed visual explanation, dynamic composition, vertical format, no text`,
    `${subject}, satisfying final result, optimistic cinematic light, vertical format, no text`,
  ];

  return VideoScriptSchema.parse({
    title: subject,
    scenes: text.map((textToSpeak, index) => ({
      sceneId: `scene-${index + 1}`,
      textToSpeak,
      imagePrompt: prompts[index],
      cameraMotion: CAMERA_MOTIONS[index],
      durationInSeconds: durationFor(textToSpeak),
      ...(index === 0
        ? {sfxTrigger: 'impact'}
        : index === 1
          ? {sfxTrigger: 'swoosh'}
          : {}),
    })),
  });
};

const SYSTEM_PROMPT = `Eres un guionista de videos verticales breves en español.
Devuelve solamente JSON válido con esta forma:
{"title":"...","scenes":[{"sceneId":"scene-1","textToSpeak":"...","imagePrompt":"...","cameraMotion":"static|pan_slow|shake_impact","durationInSeconds":4,"sfxTrigger":"impact|swoosh|riser"}]}
Usa 3 a 6 escenas, frases naturales para narración, prompts visuales sin texto y duraciones entre 2 y 12 segundos.`;

const extractJson = (text: string): unknown => {
  const fenced = text.match(/```(?:json)?\s*([\s\S]*?)```/i);
  const candidate = fenced?.[1] ?? text;
  const start = candidate.indexOf('{');
  const end = candidate.lastIndexOf('}');
  if (start === -1 || end === -1 || end <= start) {
    throw new Error('El proveedor no devolvió un objeto JSON');
  }
  return JSON.parse(candidate.slice(start, end + 1)) as unknown;
};

const generateWithGroq = async (
  topic: string,
  apiKey: string,
): Promise<VideoScript> => {
  const response = await fetch(
    'https://api.groq.com/openai/v1/chat/completions',
    {
      method: 'POST',
      headers: {
        Authorization: `Bearer ${apiKey}`,
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        model: 'llama-3.1-8b-instant',
        temperature: 0.7,
        response_format: {type: 'json_object'},
        messages: [
          {role: 'system', content: SYSTEM_PROMPT},
          {role: 'user', content: cleanTopic(topic)},
        ],
      }),
      signal: AbortSignal.timeout(30_000),
    },
  );
  if (!response.ok) {
    throw new Error(`Groq respondió ${response.status}`);
  }
  const body = (await response.json()) as {
    choices?: Array<{message?: {content?: string}}>;
  };
  const content = body.choices?.[0]?.message?.content;
  if (!content) {
    throw new Error('Groq devolvió una respuesta vacía');
  }
  return VideoScriptSchema.parse(extractJson(content));
};

const generateWithGemini = async (
  topic: string,
  apiKey: string,
): Promise<VideoScript> => {
  const endpoint =
    'https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash-lite:generateContent';
  const response = await fetch(`${endpoint}?key=${encodeURIComponent(apiKey)}`, {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({
      generationConfig: {responseMimeType: 'application/json'},
      contents: [
        {parts: [{text: `${SYSTEM_PROMPT}\n\nTema: ${cleanTopic(topic)}`}]},
      ],
    }),
    signal: AbortSignal.timeout(30_000),
  });
  if (!response.ok) {
    throw new Error(`Gemini respondió ${response.status}`);
  }
  const body = (await response.json()) as {
    candidates?: Array<{content?: {parts?: Array<{text?: string}>}}>;
  };
  const content = body.candidates?.[0]?.content?.parts?.[0]?.text;
  if (!content) {
    throw new Error('Gemini devolvió una respuesta vacía');
  }
  return VideoScriptSchema.parse(extractJson(content));
};

export const generateScript = async (
  topic: string,
  options: GenerateScriptOptions = {},
): Promise<VideoScript> => {
  const provider = options.provider ?? 'heuristic';

  try {
    if (provider === 'groq' && options.groqApiKey) {
      return await generateWithGroq(topic, options.groqApiKey);
    }
    if (provider === 'gemini' && options.geminiApiKey) {
      return await generateWithGemini(topic, options.geminiApiKey);
    }
  } catch (error) {
    const message = error instanceof Error ? error.message : String(error);
    console.warn(`Proveedor ${provider} no disponible (${message}); usando guion local.`);
  }

  return generateHeuristicScript(topic);
};
