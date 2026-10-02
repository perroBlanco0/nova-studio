import {z} from 'zod';

export const CameraMotionSchema = z.enum([
  'zoom_in',
  'pan_slow',
  'shake_impact',
]);

export const SceneSchema = z.object({
  sceneId: z.string().min(1),
  textToSpeak: z.string().min(1),
  imagePrompt: z.string().min(1),
  cameraMotion: CameraMotionSchema,
  durationInSeconds: z.number().min(1).max(30),
  sfxTrigger: z.string().min(1).optional(),
});

export const VideoScriptSchema = z.object({
  title: z.string().min(1),
  scenes: z.array(SceneSchema).min(1).max(12),
});

export type CameraMotion = z.infer<typeof CameraMotionSchema>;
export type Scene = z.infer<typeof SceneSchema>;
export type VideoScript = z.infer<typeof VideoScriptSchema>;

export const validateVideoScript = (value: unknown): VideoScript =>
  VideoScriptSchema.parse(value);
