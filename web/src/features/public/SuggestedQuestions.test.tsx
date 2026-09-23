import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import type { PopularQuestion } from "@/features/popular-questions/popularQuestionsApi";
import { SuggestedQuestions } from "./SuggestedQuestions";

// Agency ids are backend UUIDs, not the short slugs ('revenue', 'fda', ...) the
// old (now-removed) color-tint lookup assumed — keep these UUID-shaped so a
// regression back to that dead lookup would be obvious.
const questions: PopularQuestion[] = [
  { id: "q1", text: "สอบถามเรื่องภาษี", agency: { id: "11111111-1111-1111-1111-111111111111", name: "กรมสรรพากร", logo: "💰" } },
  { id: "q2", text: "ขอตรวจสอบทะเบียนยา", agency: { id: "22222222-2222-2222-2222-222222222222", name: "อย.", logo: "🏥" } },
  { id: "q3", text: "คำถามทั่วไปไม่ระบุหน่วยงาน", agency: null },
];

describe("SuggestedQuestions", () => {
  it("renders the heading", () => {
    render(<SuggestedQuestions questions={questions} onSelect={vi.fn()} />);
    expect(screen.getByText("คำถามยอดนิยม")).toBeInTheDocument();
  });

  it("renders each question's own agency logo", () => {
    render(<SuggestedQuestions questions={questions} onSelect={vi.fn()} />);
    expect(screen.getByText("💰")).toBeInTheDocument();
    expect(screen.getByText("🏥")).toBeInTheDocument();
  });

  it("does not apply a per-agency background tint class (no stable slug to key it off)", () => {
    render(<SuggestedQuestions questions={questions} onSelect={vi.fn()} />);
    const logoSpan = screen.getByText("💰");
    expect(logoSpan.className).not.toMatch(/bg-\[hsl\(var\(--gov-/);
  });

  it("renders a neutral icon when the question has no agency", () => {
    render(<SuggestedQuestions questions={questions} onSelect={vi.fn()} />);
    expect(screen.getByLabelText("ไม่ระบุหน่วยงาน")).toBeInTheDocument();
  });

  it("calls onSelect with the question text when clicked", async () => {
    const onSelect = vi.fn();
    render(<SuggestedQuestions questions={questions} onSelect={onSelect} />);
    await userEvent.click(screen.getByText("สอบถามเรื่องภาษี"));
    expect(onSelect).toHaveBeenCalledWith("สอบถามเรื่องภาษี");
  });
});
