import { render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { TextScaleProvider } from "@/shared/hooks/useTextScale";
import type { ChatMessage } from "@/shared/types";
import { ChatConversation } from "./ChatConversation";

const emptyStreaming = {
  pipelineSteps: [],
  agencyStatuses: {},
  errors: [],
  done: false,
  currentStep: "",
} as never;

const baseProps = {
  messages: [] as ChatMessage[],
  isTyping: false,
  isStreaming: false,
  activeStepCount: 0,
  currentSteps: [],
  streamingState: emptyStreaming,
  scrollRef: { current: null },
  onRate: vi.fn(),
};

describe("ChatConversation", () => {
  it("renders message bubbles", () => {
    const messages = [
      { id: "1", role: "user", content: "สวัสดี", createdAt: "" },
    ] as unknown as ChatMessage[];
    render(<ChatConversation {...baseProps} messages={messages} />);
    expect(screen.getByText("สวัสดี")).toBeInTheDocument();
  });

  it("shows the typing indicator when isTyping is true", () => {
    const { container } = render(<ChatConversation {...baseProps} isTyping />);
    expect(container.querySelector(".animate-bounce")).toBeInTheDocument();
  });

  it("scales the conversation with font-size, not zoom", () => {
    window.localStorage.setItem("chat-text-scale", "large");
    const { container } = render(
      <TextScaleProvider>
        <ChatConversation {...baseProps} />
      </TextScaleProvider>,
    );
    const wrapper = container.querySelector<HTMLElement>(".max-w-3xl");
    expect(wrapper).not.toBeNull();
    expect(wrapper!.style.fontSize).toBe("1.25em");
    expect(wrapper!.style.zoom).toBeFalsy();
  });
});

afterEach(() => window.localStorage.clear());
