import { afterEach, describe, expect, it } from "vitest";

import { resetMockData } from "@/mocks/fixtures";
import {
  createPopularQuestion,
  deletePopularQuestion,
  fetchPublicPopularQuestions,
  listPopularQuestions,
  regeneratePopularQuestions,
  updatePopularQuestion,
} from "./popularQuestionsApi";

afterEach(() => resetMockData());

describe("popularQuestionsApi", () => {
  it("fetchPublicPopularQuestions unwraps the { questions } envelope and hides hidden rows", async () => {
    const questions = await fetchPublicPopularQuestions();
    expect(questions.map((q) => q.id)).toEqual(["pq-1", "pq-2"]);
    expect(questions[0]).not.toHaveProperty("source");
  });

  it("listPopularQuestions returns the full admin rows including hidden ones", async () => {
    const questions = await listPopularQuestions();
    expect(questions).toHaveLength(3);
    expect(questions.find((q) => q.id === "pq-3")?.hidden).toBe(true);
  });

  it("createPopularQuestion posts to /api/v1/popular-questions and returns the created row", async () => {
    const created = await createPopularQuestion({ text: "คำถามใหม่", agency_id: null });
    expect(created.text).toBe("คำถามใหม่");
    expect(created.source).toBe("manual");
    expect((await listPopularQuestions()).some((q) => q.id === created.id)).toBe(true);
  });

  it("updatePopularQuestion patches the row", async () => {
    const updated = await updatePopularQuestion("pq-2", { pinned: true });
    expect(updated.pinned).toBe(true);
  });

  it("deletePopularQuestion removes the row", async () => {
    await deletePopularQuestion("pq-2");
    expect((await listPopularQuestions()).find((q) => q.id === "pq-2")).toBeUndefined();
  });

  it("regeneratePopularQuestions posts to the regenerate endpoint", async () => {
    await expect(regeneratePopularQuestions()).resolves.not.toThrow();
  });
});
