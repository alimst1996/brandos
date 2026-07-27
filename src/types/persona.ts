/**
 * A Persona represents a brand communication profile — voice, tone,
 * audience, and style guidelines used to generate on-brand content.
 */

export interface PersonaTone {
  label: string;
  intensity: number;
}

export interface Persona {
  id: string;
  name: string;
  tagline: string;
  avatar: string;
  color: string;
  voice: string;
  tones: PersonaTone[];
  audience: string;
  values: string[];
  styleGuide: string;
  channels: string[];
  languages: string[];
  sampleResponse: string;
  createdAt: string;
  updatedAt: string;
}
