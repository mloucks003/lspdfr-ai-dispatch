/**
 * Priority color mapping for CAD calls.
 * Priority 1 = high (red), 2 = medium (yellow), 3 = low (green).
 */

const PRIORITY_COLORS: Record<number, string> = {
  1: "red",
  2: "yellow",
  3: "green",
};

export function getPriorityColor(priority: number): string {
  return PRIORITY_COLORS[priority] ?? "gray";
}
