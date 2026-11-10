/** @file Deterministic viewport driver for activity lookup tests. */
/** Deliver exact viewport transitions while retaining the real rendered marks. */
export class ControlledIntersectionObserver implements IntersectionObserver {
  static instances: ControlledIntersectionObserver[] = [];

  readonly root: Element | Document | null = null;
  readonly rootMargin = '0px';
  readonly scrollMargin = '0px';
  readonly thresholds: ReadonlyArray<number> = [0];
  readonly observed = new Set<Element>();
  disconnected = false;

  constructor(
    private readonly callback: IntersectionObserverCallback,
    _options?: IntersectionObserverInit
  ) {
    ControlledIntersectionObserver.instances.push(this);
  }

  observe(target: Element): void {
    this.observed.add(target);
  }

  unobserve(target: Element): void {
    this.observed.delete(target);
  }

  disconnect(): void {
    this.disconnected = true;
    this.observed.clear();
  }

  takeRecords(): IntersectionObserverEntry[] {
    return [];
  }

  /** Mark an observed session button as entering or leaving the viewport. */
  setVisibility(target: Element, isIntersecting: boolean): void {
    if (!this.observed.has(target)) throw new Error('Only observed marks can change visibility.');
    const bounds = target.getBoundingClientRect();
    this.callback(
      [
        {
          target,
          isIntersecting,
          intersectionRatio: isIntersecting ? 1 : 0,
          time: 0,
          rootBounds: null,
          boundingClientRect: bounds,
          intersectionRect: bounds
        }
      ],
      this
    );
  }
}
