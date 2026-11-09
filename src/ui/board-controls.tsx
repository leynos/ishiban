/** @file Render local search, activity, density, and presentation controls. */
import type {ReactElement} from 'react';
import {activityFilterOf, ACTIVITIES, type ActivityFilter, type Density, type Presentation} from './board-model';

interface BoardControlsProps {
  readonly query: string;
  readonly activityFilter: ActivityFilter;
  readonly includeArchived: boolean;
  readonly density: Density;
  readonly presentation: Presentation;
  readonly onQueryChange: (query: string) => void;
  readonly onActivityChange: (activity: ActivityFilter) => void;
  readonly onArchivedChange: (includeArchived: boolean) => void;
  readonly onDensityChange: () => void;
  readonly onPresentationChange: (presentation: Presentation) => void;
  readonly onReset: () => void;
}

/** Return the readable button label for a board presentation mode. */
function presentationLabel(presentation: Presentation): string {
  switch (presentation) {
    case 'panorama': {
      return 'Panorama';
    }
    case 'matrix': {
      return 'Matrix';
    }
    case 'list': {
      return 'List';
    }
  }
}

/**
 * Render accessible search, activity, archive, density, and mode controls.
 * @param props Controlled values and callbacks owned by the board component.
 * @returns Native controls styled with semantic daisyUI classes.
 */
export function BoardControls(props: BoardControlsProps): ReactElement {
  const {
    query,
    activityFilter,
    includeArchived,
    density,
    presentation,
    onQueryChange,
    onActivityChange,
    onArchivedChange,
    onDensityChange,
    onPresentationChange,
    onReset
  } = props;
  return (
    <section aria-label="Board controls" className="board-controls">
      <label className="search-control">
        <span>Find repository, session or branch</span>
        <input
          aria-label="Find repository, session or branch"
          className="input input-bordered"
          onChange={(event) => onQueryChange(event.currentTarget.value)}
          placeholder="Search the workspace"
          type="search"
          value={query}
        />
      </label>
      <label className="activity-control">
        <span>Activity</span>
        <select
          aria-label="Filter by activity"
          className="select select-bordered"
          onChange={(event) => onActivityChange(activityFilterOf(event.currentTarget.value))}
          value={activityFilter}
        >
          <option value="all">All activity</option>
          {ACTIVITIES.map((activity) => (
            <option key={activity} value={activity}>
              {activity}
            </option>
          ))}
        </select>
      </label>
      <label className="archived-control">
        <input
          checked={includeArchived}
          className="checkbox checkbox-primary"
          onChange={(event) => onArchivedChange(event.currentTarget.checked)}
          type="checkbox"
        />
        <span>Include archived and removed</span>
      </label>
      <fieldset className="density-control">
        <legend>Mark density</legend>
        <button
          aria-pressed={density === 'comfortable'}
          className="btn btn-outline"
          onClick={onDensityChange}
          type="button"
        >
          {density === 'comfortable' ? 'Comfortable marks' : 'Overview marks'}
        </button>
      </fieldset>
      <fieldset className="presentation-control">
        <legend>Board presentation</legend>
        {(['panorama', 'matrix', 'list'] as const).map((option) => (
          <button
            aria-pressed={presentation === option}
            className={presentation === option ? 'btn btn-primary' : 'btn btn-outline'}
            key={option}
            onClick={() => onPresentationChange(option)}
            type="button"
          >
            {presentationLabel(option)}
          </button>
        ))}
      </fieldset>
      <button className="btn btn-ghost reset-control" onClick={onReset} type="button">
        Reset filters
      </button>
    </section>
  );
}
