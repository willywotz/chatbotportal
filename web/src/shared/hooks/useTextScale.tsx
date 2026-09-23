import {
  createContext,
  useCallback,
  useContext,
  useMemo,
  useState,
  type ReactNode,
} from "react";

export type TextScale = "small" | "normal" | "large";

const SCALE_FACTOR: Record<TextScale, number> = {
  small: 0.875,
  normal: 1,
  large: 1.25,
};

const STORAGE_KEY = "chat-text-scale";

interface TextScaleContextValue {
  scale: TextScale;
  factor: number;
  setScale: (scale: TextScale) => void;
}

const TextScaleContext = createContext<TextScaleContextValue>({
  scale: "normal",
  factor: 1,
  setScale: () => {},
});

function readStoredScale(): TextScale {
  if (typeof window === "undefined") return "normal";
  const stored = window.localStorage.getItem(STORAGE_KEY);
  return stored === "small" || stored === "large" ? stored : "normal";
}

export function TextScaleProvider({ children }: { children: ReactNode }) {
  const [scale, setScaleState] = useState<TextScale>(readStoredScale);

  const setScale = useCallback((next: TextScale) => {
    setScaleState(next);
    window.localStorage.setItem(STORAGE_KEY, next);
  }, []);

  const value = useMemo(
    () => ({ scale, factor: SCALE_FACTOR[scale], setScale }),
    [scale, setScale],
  );

  return <TextScaleContext.Provider value={value}>{children}</TextScaleContext.Provider>;
}

export function useTextScale() {
  return useContext(TextScaleContext);
}
