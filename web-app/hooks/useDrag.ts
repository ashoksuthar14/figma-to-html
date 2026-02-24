"use client";

import { useCallback, useRef, useEffect } from "react";

interface UseDragOptions {
  onStart: (x: number, y: number) => void;
  onMove: (x: number, y: number) => void;
  onEnd: () => void;
}

export function useDrag({ onStart, onMove, onEnd }: UseDragOptions) {
  const onStartRef = useRef(onStart);
  const onMoveRef = useRef(onMove);
  const onEndRef = useRef(onEnd);
  const rafRef = useRef<number | null>(null);
  const isDraggingRef = useRef(false);
  const pendingMove = useRef<{ x: number; y: number } | null>(null);

  useEffect(() => {
    onStartRef.current = onStart;
    onMoveRef.current = onMove;
    onEndRef.current = onEnd;
  });

  const handlePointerMove = useCallback((e: PointerEvent) => {
    if (!isDraggingRef.current) return;
    e.preventDefault();
    pendingMove.current = { x: e.clientX, y: e.clientY };
    if (rafRef.current === null) {
      rafRef.current = requestAnimationFrame(() => {
        rafRef.current = null;
        if (pendingMove.current) {
          onMoveRef.current(pendingMove.current.x, pendingMove.current.y);
          pendingMove.current = null;
        }
      });
    }
  }, []);

  const handlePointerUp = useCallback((e: PointerEvent) => {
    if (!isDraggingRef.current) return;
    isDraggingRef.current = false;
    if (rafRef.current !== null) {
      cancelAnimationFrame(rafRef.current);
      rafRef.current = null;
    }
    if (pendingMove.current) {
      onMoveRef.current(pendingMove.current.x, pendingMove.current.y);
      pendingMove.current = null;
    }
    window.removeEventListener("pointermove", handlePointerMove);
    window.removeEventListener("pointerup", handlePointerUp);
    onEndRef.current();
  }, [handlePointerMove]);

  const handlePointerDown = useCallback(
    (e: React.PointerEvent) => {
      e.preventDefault();
      e.stopPropagation();
      isDraggingRef.current = true;
      onStartRef.current(e.clientX, e.clientY);
      window.addEventListener("pointermove", handlePointerMove);
      window.addEventListener("pointerup", handlePointerUp);
    },
    [handlePointerMove, handlePointerUp]
  );

  useEffect(() => {
    return () => {
      if (rafRef.current !== null) cancelAnimationFrame(rafRef.current);
      window.removeEventListener("pointermove", handlePointerMove);
      window.removeEventListener("pointerup", handlePointerUp);
    };
  }, [handlePointerMove, handlePointerUp]);

  return { handlePointerDown };
}
