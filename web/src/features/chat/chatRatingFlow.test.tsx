import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import type { ChatMessage } from "@/shared/types";

import { MessageBubble } from "./MessageBubble";

const assistantMessage: ChatMessage = {
  id: "m1",
  role: "assistant",
  content: "คำตอบทดสอบจากระบบ",
  timestamp: "10:00",
  rating: null,
};

describe("chat rating workflow (MessageBubble + FeedbackDialog)", () => {
  it("calls onRate with 'up' when the user clicks thumbs up", async () => {
    const onRate = vi.fn();
    render(<MessageBubble message={assistantMessage} onRate={onRate} />);

    const buttons = screen.getAllByRole("button");
    expect(buttons).toHaveLength(2);

    await userEvent.click(buttons[0]);
    expect(onRate).toHaveBeenCalledWith("m1", "up");
  });

  it("opens the feedback dialog on thumbs down and submits the typed reason", async () => {
    const onRate = vi.fn();
    render(<MessageBubble message={assistantMessage} onRate={onRate} />);

    await userEvent.click(screen.getAllByRole("button")[1]);

    expect(screen.getByText("ขอบคุณสำหรับ Feedback")).toBeInTheDocument();

    await userEvent.type(
      screen.getByPlaceholderText(/คำตอบไม่ตรงประเด็น/),
      "ข้อมูลไม่ถูกต้อง",
    );
    await userEvent.click(screen.getByRole("button", { name: "ส่ง Feedback" }));

    expect(onRate).toHaveBeenCalledWith("m1", "down", "ข้อมูลไม่ถูกต้อง");
  });

  it("submits a down rating with no reason when the user skips the dialog", async () => {
    const onRate = vi.fn();
    render(<MessageBubble message={assistantMessage} onRate={onRate} />);

    await userEvent.click(screen.getAllByRole("button")[1]);
    await userEvent.click(screen.getByRole("button", { name: "ข้าม" }));

    expect(onRate).toHaveBeenCalledWith("m1", "down", undefined);
  });

  it("shows the thank-you state and hides the rating buttons once rated", () => {
    render(
      <MessageBubble message={{ ...assistantMessage, rating: "up" }} onRate={vi.fn()} />,
    );

    expect(screen.getByText("👍 ขอบคุณสำหรับ feedback!")).toBeInTheDocument();
    expect(screen.queryByRole("button")).not.toBeInTheDocument();
  });
});
