// All content below is MOCK and unvalidated. Rohingya strings are placeholders,
// not verified translations (see README: data must be marked unvalidated).
import type { Category, Scenario, Word } from './types';

export const categories: Category[] = [
  { id: 'healthcare', name: 'Healthcare', description: 'Hospitals, clinics, appointments' },
  { id: 'daily_life', name: 'Daily Life', description: 'Greetings, shopping, requests' },
  { id: 'transportation', name: 'Transportation', description: 'Bus, tickets, directions' },
  { id: 'employment', name: 'Employment', description: 'Jobs, schedules, workplace' },
  { id: 'family', name: 'Family', description: 'People at home' },
];

const w = (id: string, categoryId: string, english: string, rohingyalish: string | null): Word => ({
  id,
  categoryId,
  english,
  rohingyalish,
  rohingya: null,
  imageUrl: null,
  audioUrl: null,
  verification: 'unvalidated',
});

export const words: Word[] = [
  w('word_001', 'healthcare', 'Doctor', '[mock] dakhtor'),
  w('word_002', 'healthcare', 'Hospital', '[mock] haspatal'),
  w('word_003', 'healthcare', 'Medicine', '[mock] oshud'),
  w('word_004', 'daily_life', 'Hello', '[mock] salam'),
  w('word_005', 'daily_life', 'Thank you', '[mock] shukria'),
  w('word_006', 'daily_life', 'Water', '[mock] pani'),
  w('word_007', 'transportation', 'Bus', '[mock] bas'),
  w('word_008', 'transportation', 'Ticket', null),
  w('word_009', 'employment', 'Job', '[mock] kam'),
  w('word_010', 'employment', 'Boss', null),
  w('word_011', 'family', 'Mother', '[mock] amma'),
  w('word_012', 'family', 'Father', '[mock] abba'),
];

export const scenarios: Scenario[] = [
  {
    id: 'doctor_visit',
    title: 'At the doctor',
    turns: [
      { id: 't1', role: 'partner', text: 'Hello! How can I help you today?' },
      { id: 't2', role: 'partner', text: 'Where does it hurt?' },
      { id: 't3', role: 'partner', text: 'How long have you felt this way?' },
    ],
  },
];

export const mockTranslations: Record<string, string> = {
  'en-rhg': '[mock] Rohingya translation',
  'rhg-en': 'I need to see a doctor.',
};

export const mockOcrText = 'Where is the nearest clinic?';
