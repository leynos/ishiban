/** @file Deterministic viewport driver for activity lookup tests. */
import type {BoardStore} from '../src/client';
import {startLazyActivity} from '../src/lazy-activity';

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

/**
 * Replace browser visibility with the controllable observer for one test.
 * @returns Cleanup restoring the exact prior global descriptor.
 * @example
 * const restore = installControlledIntersectionObserver(); restore();
 */
export function installControlledIntersectionObserver(): () => void {
  const prior = Object.getOwnPropertyDescriptor(globalThis, 'IntersectionObserver');
  Object.defineProperty(globalThis, 'IntersectionObserver', {
    configurable: true,
    value: ControlledIntersectionObserver
  });
  ControlledIntersectionObserver.instances = [];
  return () => {
    if (prior) Object.defineProperty(globalThis, 'IntersectionObserver', prior);
    else Reflect.deleteProperty(globalThis, 'IntersectionObserver');
    ControlledIntersectionObserver.instances = [];
  };
}

/**
 * Start real activity scanning against the installed controlled observer.
 * @param store The board store whose unknown sessions can be resolved.
 * @returns The observer for viewport transitions and the scanner cleanup.
 * @throws {Error} When the controlled observer was not installed first.
 * @example
 * const {observer, stop} = startControlledActivity(store);
 * observer.setVisibility(mark, true);
 * stop();
 */
export function startControlledActivity(store: BoardStore) {
  const stop = startLazyActivity(store);
  const observer = ControlledIntersectionObserver.instances.at(-1);
  if (!observer) {
    stop();
    throw new Error('The activity scanner needs its controlled viewport observer.');
  }
  return {observer, stop};
}
