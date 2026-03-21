import { useCallback, useMemo, useState } from "react";

type UseMeasuredVirtualWindowArgs = {
  estimatedItemHeight: number;
  itemCount: number;
  overscan: number;
  prefixHeight?: number;
  scrollTop: number;
  viewportHeight: number;
};

type VirtualWindowResult = {
  bottomSpacerHeight: number;
  endIndex: number;
  onItemHeightChange: (index: number, height: number) => void;
  resetMeasurements: () => void;
  startIndex: number;
  topSpacerHeight: number;
  visibleIndexes: number[];
};

export function useMeasuredVirtualWindow({
  estimatedItemHeight,
  itemCount,
  overscan,
  prefixHeight = 0,
  scrollTop,
  viewportHeight,
}: UseMeasuredVirtualWindowArgs): VirtualWindowResult {
  const [itemHeights, setItemHeights] = useState<Record<number, number>>({});

  const onItemHeightChange = useCallback((index: number, height: number) => {
    const normalizedHeight = Math.max(0, Math.round(height));
    setItemHeights((prev) => {
      if (prev[index] === normalizedHeight) {
        return prev;
      }
      return {
        ...prev,
        [index]: normalizedHeight,
      };
    });
  }, []);

  const resetMeasurements = useCallback(() => {
    setItemHeights({});
  }, []);

  const virtualWindow = useMemo(() => {
    if (itemCount === 0) {
      return {
        startIndex: 0,
        endIndex: -1,
        topSpacerHeight: 0,
        bottomSpacerHeight: 0,
      };
    }

    const offsets: number[] = new Array(itemCount);
    const heights: number[] = new Array(itemCount);
    let totalHeight = 0;

    for (let index = 0; index < itemCount; index += 1) {
      offsets[index] = totalHeight;
      const height = itemHeights[index] ?? estimatedItemHeight;
      heights[index] = height;
      totalHeight += height;
    }

    const adjustedScrollTop = Math.min(
      Math.max(0, scrollTop - prefixHeight),
      Math.max(0, totalHeight - Math.max(viewportHeight, 1)),
    );
    const viewportStart = Math.max(0, adjustedScrollTop - overscan);
    const viewportEnd = adjustedScrollTop + Math.max(viewportHeight, 1) + overscan;

    let startIndex = 0;
    while (
      startIndex < itemCount &&
      offsets[startIndex] + heights[startIndex] < viewportStart
    ) {
      startIndex += 1;
    }
    startIndex = Math.min(startIndex, itemCount - 1);

    let endIndex = startIndex;
    while (endIndex < itemCount && offsets[endIndex] < viewportEnd) {
      endIndex += 1;
    }
    endIndex = Math.max(startIndex, Math.min(itemCount - 1, endIndex));

    const topSpacerHeight = offsets[startIndex] ?? 0;
    const renderedEndOffset = offsets[endIndex] + heights[endIndex];
    const bottomSpacerHeight = Math.max(0, totalHeight - renderedEndOffset);

    return {
      startIndex,
      endIndex,
      topSpacerHeight,
      bottomSpacerHeight,
    };
  }, [
    estimatedItemHeight,
    itemCount,
    itemHeights,
    overscan,
    prefixHeight,
    scrollTop,
    viewportHeight,
  ]);

  const visibleIndexes = useMemo(() => {
    if (virtualWindow.endIndex < virtualWindow.startIndex) {
      return [] as number[];
    }

    return Array.from(
      { length: virtualWindow.endIndex - virtualWindow.startIndex + 1 },
      (_, index) => virtualWindow.startIndex + index,
    );
  }, [virtualWindow.endIndex, virtualWindow.startIndex]);

  return {
    ...virtualWindow,
    visibleIndexes,
    onItemHeightChange,
    resetMeasurements,
  };
}
