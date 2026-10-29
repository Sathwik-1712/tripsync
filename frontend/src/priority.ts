import type { Priority } from "./api";

// How each budget priority is shown, and the phrase sent to the backend's intake parser.
export const PRIORITIES: Priority[] = ["balanced", "stay", "travel", "food", "experiences"];
export const PRIORITY_LABEL: Record<Priority, string> = {
  balanced: "Balanced", stay: "Nicer stay", travel: "Faster travel", food: "Better food", experiences: "More experiences",
};
export const PRIORITY_PHRASE: Record<Priority, string> = {
  balanced: "keep it balanced", stay: "nicer stay", travel: "faster travel", food: "better food",
  experiences: "more experiences",
};
