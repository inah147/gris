// calendar.js — componente Calendário do design system Basecoat.
// Modos: month, week (com/sem horários), list.
// Click em card dispara CustomEvent("gris:calendar:event-click").

(() => {
  const MS_PER_DAY = 86400000;
  const MAX_MONTH_LANES_DESKTOP = 3;
  const MAX_MONTH_LANES_MOBILE = 2;
  const MOBILE_BREAKPOINT = 640;
  const DEFAULT_EVENT_DURATION_MIN = 30;

  const isMobile = () => window.innerWidth < MOBILE_BREAKPOINT;

  const LUCIDE_SPRITE = "/assets/gris/design_system/icons/lucide/sprite.svg";

  const createLucideIcon = (name, color) => {
    const SVG_NS = "http://www.w3.org/2000/svg";
    const svg = document.createElementNS(SVG_NS, "svg");
    // Usa `ds-lucide` para herdar stroke/fill/linecap padrão dos ícones Lucide
    // do design system, mais a classe própria pra dimensão dentro do card.
    svg.setAttribute("class", "ds-lucide calendar-event-card__icon");
    svg.setAttribute("aria-hidden", "true");
    svg.setAttribute("focusable", "false");
    svg.setAttribute("viewBox", "0 0 24 24");
    if (color) svg.style.setProperty("--cal-event-icon-color", color);
    const use = document.createElementNS(SVG_NS, "use");
    use.setAttribute("href", `${LUCIDE_SPRITE}#${name}`);
    svg.appendChild(use);
    return svg;
  };

  // -------- Date helpers --------------------------------------------------

  const parseISO = (value) => {
    if (!value) return null;
    if (value instanceof Date) return new Date(value.getTime());
    const str = String(value);
    // Trata "YYYY-MM-DD" sempre como data LOCAL — `new Date("2026-05-01")` parsearia
    // como UTC midnight, o que vira 30/04 em fusos horários negativos (ex.: UTC-3).
    const dateOnly = str.match(/^(\d{4})-(\d{2})-(\d{2})$/);
    if (dateOnly) {
      return new Date(Number(dateOnly[1]), Number(dateOnly[2]) - 1, Number(dateOnly[3]));
    }
    const d = new Date(str);
    return Number.isNaN(d.getTime()) ? null : d;
  };

  const startOfDay = (d) => new Date(d.getFullYear(), d.getMonth(), d.getDate());
  const endOfDay = (d) => new Date(d.getFullYear(), d.getMonth(), d.getDate(), 23, 59, 59, 999);
  const addDays = (d, n) => {
    const r = new Date(d);
    r.setDate(r.getDate() + n);
    return r;
  };
  const isWeekendDate = (date) => date.getDay() === 0 || date.getDay() === 6;
  const addMonths = (d, n) => {
    const r = new Date(d);
    r.setMonth(r.getMonth() + n);
    return r;
  };
  const startOfMonth = (d) => new Date(d.getFullYear(), d.getMonth(), 1);
  const endOfMonth = (d) => endOfDay(new Date(d.getFullYear(), d.getMonth() + 1, 0));
  const formatISODate = (d) => {
    const year = d.getFullYear();
    const month = String(d.getMonth() + 1).padStart(2, "0");
    const day = String(d.getDate()).padStart(2, "0");
    return `${year}-${month}-${day}`;
  };
  const isSameDay = (a, b) =>
    a && b && a.getFullYear() === b.getFullYear() && a.getMonth() === b.getMonth() && a.getDate() === b.getDate();
  const isSameMonth = (a, b) =>
    a && b && a.getFullYear() === b.getFullYear() && a.getMonth() === b.getMonth();

  const startOfWeek = (date, firstWeekday) => {
    const d = startOfDay(date);
    const diff = (d.getDay() - firstWeekday + 7) % 7;
    return addDays(d, -diff);
  };

  const daysBetween = (a, b) => Math.round((startOfDay(b) - startOfDay(a)) / MS_PER_DAY);

  // -------- Event normalization & filtering ------------------------------

  const normalizeEvent = (raw) => {
    const start = parseISO(raw.start);
    const end = raw.end ? parseISO(raw.end) : null;
    const startHasTime = raw.start && String(raw.start).includes("T");
    const endHasTime = raw.end && String(raw.end).includes("T");
    const allDay = raw.all_day !== undefined ? !!raw.all_day : !startHasTime;
    return {
      id: raw.id,
      title: raw.title || "",
      start,
      end,
      startHasTime,
      endHasTime,
      allDay,
      category: raw.category || null,
      color: raw.color || null,
      icon: raw.icon || null,
      iconColor: raw.icon_color || null,
      data: raw.data || {},
      raw,
    };
  };

  const eventOverlapsRange = (event, rangeStart, rangeEnd) => {
    if (!event.start) return false;
    const evtStart = event.start;
    const evtEnd = event.end || event.start;
    return evtStart <= rangeEnd && evtEnd >= rangeStart;
  };

  const isMultiDayEvent = (event) => {
    if (!event.start) return false;
    const evtEnd = event.end || event.start;
    return startOfDay(evtEnd) > startOfDay(event.start);
  };

  // -------- Formatting ---------------------------------------------------

  const fmtCache = new Map();
  const getFormatter = (locale, opts) => {
    const key = locale + JSON.stringify(opts);
    if (!fmtCache.has(key)) fmtCache.set(key, new Intl.DateTimeFormat(locale, opts));
    return fmtCache.get(key);
  };

  const formatTime = (date, locale) =>
    getFormatter(locale, { hour: "2-digit", minute: "2-digit" }).format(date);

  const formatTimeRange = (event, locale) => {
    if (event.allDay || !event.startHasTime) return "";
    const start = formatTime(event.start, locale);
    if (event.end && event.endHasTime) return `${start} – ${formatTime(event.end, locale)}`;
    return start;
  };

  const capitalize = (s) => (s ? s.charAt(0).toUpperCase() + s.slice(1) : s);

  // -------- DOM helpers --------------------------------------------------

  const el = (tag, opts = {}, children = []) => {
    const node = document.createElement(tag);
    if (opts.class) node.className = opts.class;
    if (opts.text != null) node.textContent = opts.text;
    if (opts.html != null) node.innerHTML = opts.html;
    if (opts.attrs) {
      for (const [k, v] of Object.entries(opts.attrs)) {
        if (v === false || v == null) continue;
        node.setAttribute(k, v === true ? "" : v);
      }
    }
    if (opts.style) {
      for (const [k, v] of Object.entries(opts.style)) node.style.setProperty(k, v);
    }
    if (opts.dataset) {
      for (const [k, v] of Object.entries(opts.dataset)) node.dataset[k] = v;
    }
    for (const child of [].concat(children)) {
      if (child == null || child === false) continue;
      node.appendChild(child instanceof Node ? child : document.createTextNode(child));
    }
    return node;
  };

  // -------- Lane assignment (for overlapping events) --------------------

  // Generic interval-lanes assignment.
  // intervals: [{key, lo, hi, ...rest}] (lo/hi inclusive).
  // Returns array same length, each with `lane` index assigned.
  const assignLanes = (intervals) => {
    const sorted = [...intervals].sort((a, b) => a.lo - b.lo || b.hi - a.hi);
    const lanes = [];
    for (const item of sorted) {
      let placed = false;
      for (let i = 0; i < lanes.length; i += 1) {
        const last = lanes[i][lanes[i].length - 1];
        if (last.hi < item.lo) {
          lanes[i].push(item);
          item.lane = i;
          placed = true;
          break;
        }
      }
      if (!placed) {
        item.lane = lanes.length;
        lanes.push([item]);
      }
    }
    return { items: sorted, laneCount: lanes.length };
  };

  // -------- Event card factory ------------------------------------------

  const createEventCard = (event, options = {}) => {
    const card = el("button", {
      class: "calendar-event-card",
      attrs: {
        type: "button",
        role: "button",
        tabindex: "0",
        "data-calendar-event-id": event.id,
        "aria-label": `${event.title}${formatTimeRange(event, options.locale) ? ", " + formatTimeRange(event, options.locale) : ""}`,
      },
      style: {
        "--cal-cat-color": event.color || options.colorOf?.(event.category) || "var(--primary)",
      },
    });

    if (event.icon) {
      card.appendChild(createLucideIcon(event.icon, event.iconColor));
    }
    const showTime = options.showTime && formatTimeRange(event, options.locale);
    if (showTime) {
      card.appendChild(el("span", { class: "calendar-event-card__time", text: formatTimeRange(event, options.locale) }));
    }
    card.appendChild(el("span", { class: "calendar-event-card__title", text: event.title }));

    if (options.continuedLeft) card.classList.add("calendar-event-card--continued-left");
    if (options.continuedRight) card.classList.add("calendar-event-card--continued-right");
    if (options.multiDay) card.classList.add("calendar-event-card--multi-day");

    if (options.style) {
      for (const [k, v] of Object.entries(options.style)) card.style.setProperty(k, v);
    }

    return card;
  };

  const buildDayIntervals = (events, rangeStart, rangeEnd) => {
    const lastOffset = daysBetween(rangeStart, rangeEnd);
    return events.reduce((intervals, event) => {
      if (!eventOverlapsRange(event, rangeStart, rangeEnd)) return intervals;

      const evtStart = startOfDay(event.start);
      const evtEnd = startOfDay(event.end || event.start);
      intervals.push({
        event,
        lo: Math.max(0, daysBetween(rangeStart, evtStart)),
        hi: Math.min(lastOffset, daysBetween(rangeStart, evtEnd)),
      });
      return intervals;
    }, []);
  };

  const createWeekAllDayBand = ({ weekStart, weekEnd, events, colorOf, locale, showAxisLabel = true }) => {
    const band = el("div", {
      class: showAxisLabel ? "calendar__week-allday" : "calendar__week-allday calendar__week-allday--no-axis",
    });

    if (showAxisLabel) {
      band.appendChild(el("div", { class: "calendar__week-allday-label", text: "Dia inteiro" }));
    }

    const content = el("div", { class: "calendar__week-allday-content" });
    const cells = el("div", { class: "calendar__week-allday-cells" });

    for (let d = 0; d < 7; d += 1) {
      const dayDate = addDays(weekStart, d);
      cells.appendChild(el("div", {
        class: [
          "calendar__week-allday-cell",
          isWeekendDate(dayDate) ? "calendar__week-allday-cell--weekend" : "calendar__week-allday-cell--weekday",
        ].join(" "),
      }));
    }

    content.appendChild(cells);

    const { items, laneCount } = assignLanes(buildDayIntervals(events, weekStart, weekEnd));
    const layer = el("div", { class: "calendar__week-allday-events" });
    const cardHeight = 24;
    const gap = 2;
    const bandHeight = Math.max(cardHeight + 8, 8 + laneCount * cardHeight + Math.max(0, laneCount - 1) * gap);

    band.style.setProperty("--cal-week-span-height", `${bandHeight}px`);

    for (const item of items) {
      const continuedLeft = item.event.start < weekStart;
      const continuedRight = (item.event.end || item.event.start) > weekEnd;
      const card = createEventCard(item.event, {
        colorOf,
        locale,
        multiDay: item.lo !== item.hi,
        continuedLeft,
        continuedRight,
      });
      card.style.left = `calc(${(item.lo / 7) * 100}% + 2px)`;
      card.style.width = `calc(${((item.hi - item.lo + 1) / 7) * 100}% - 4px)`;
      card.style.top = `${4 + item.lane * (cardHeight + gap)}px`;
      layer.appendChild(card);
    }

    content.appendChild(layer);
    band.appendChild(content);

    return band;
  };

  // -------- Init ---------------------------------------------------------

  const initCalendar = (root) => {
    if (root.dataset.calendarInitialized === "true") return;

    const configEl = root.querySelector('script[data-calendar-config]');
    const eventsEl = root.querySelector('script[data-calendar-events]');
    if (!configEl || !eventsEl) {
      console.error("Calendar: missing config or events script.", root);
      return;
    }

    let config;
    let rawEvents;
    try {
      config = JSON.parse(configEl.textContent || "{}");
      rawEvents = JSON.parse(eventsEl.textContent || "[]");
    } catch (e) {
      console.error("Calendar: failed to parse inline JSON.", e);
      return;
    }

    const body = root.querySelector("[data-calendar-body]");
    const periodLabel = root.querySelector("[data-calendar-period-label]");
    const modeToggle = root.querySelector("[data-calendar-mode-toggle]");
    const navPrev = root.querySelector("[data-calendar-nav-prev]");
    const navNext = root.querySelector("[data-calendar-nav-next]");
    const navToday = root.querySelector("[data-calendar-nav-today]");
    const filtersWrap = root.querySelector("[data-calendar-filters]");
    const filtersToggle = root.querySelector("[data-calendar-filters-toggle]");
    const filtersCount = root.querySelector("[data-calendar-filters-count]");
    const weekHoursToggle = root.querySelector("[data-calendar-week-hours-toggle]");
    const weekHoursCheckbox = root.querySelector("[data-calendar-week-hours-checkbox]");
    const listControls = root.querySelector("[data-calendar-list-controls]");
    const listVariantToggle = root.querySelector("[data-calendar-list-variant-toggle]");
    const listShowAllDaysCheckbox = root.querySelector("[data-calendar-list-show-all-days-control] input[type='checkbox']");

    // -------- State -----------------------------------------------------

    const allowedModes = config.allowedModes || ["month", "week", "list"];
    const initialMode = allowedModes.includes(config.initialMode) ? config.initialMode : allowedModes[0];
    const allowedListVariants = ["default", "category"];
    const initialListVariant = allowedListVariants.includes(config.initialListVariant)
      ? config.initialListVariant
      : "default";

    let mode = (!config.initialMode && isMobile() && allowedModes.includes("list")) ? "list" : initialMode;
    let anchorDate = config.initialDate ? parseISO(config.initialDate) : startOfDay(new Date());
    if (!anchorDate) anchorDate = startOfDay(new Date());

    let events = rawEvents.map(normalizeEvent);
    const categories = config.categories || [];
    const categoryMap = new Map(categories.map((c) => [c.name, c]));
    const activeCategories = new Set(categories.map((c) => c.name));
    let weekShowHours = !!config.weekShowHours;
    let listVariant = initialListVariant;
    let listShowAllDays = !!config.listShowAllDays;
    let listRangeStart = config.listRangeStart ? parseISO(config.listRangeStart) : null;
    let listRangeEnd = config.listRangeEnd ? parseISO(config.listRangeEnd) : null;
    const hourRange = Array.isArray(config.hourRange) && config.hourRange.length === 2
      ? config.hourRange : [0, 24];
    const firstWeekday = Number.isInteger(config.firstWeekday) ? config.firstWeekday : 0;
    const locale = config.locale || "pt-BR";

    if (listRangeStart) listRangeStart = startOfDay(listRangeStart);
    if (listRangeEnd) listRangeEnd = endOfDay(listRangeEnd);
    if (listRangeStart && listRangeEnd && listRangeEnd < listRangeStart) {
      const previousStart = listRangeStart;
      listRangeStart = startOfDay(listRangeEnd);
      listRangeEnd = endOfDay(previousStart);
    }

    const colorOf = (catName) => {
      if (!catName) return "var(--primary)";
      const c = categoryMap.get(catName);
      return c?.color || "var(--primary)";
    };

    // -------- Filter helper --------------------------------------------

    const filteredEvents = () => events.filter((e) => {
      if (!e.category) return true;
      return activeCategories.has(e.category);
    });

    // -------- Renderers -------------------------------------------------

    const setPeriodLabel = (text) => {
      if (periodLabel) periodLabel.textContent = text;
    };

    const getListRange = () => {
      const boundary = listRangeStart || listRangeEnd || anchorDate;
      let start = listRangeStart ? startOfDay(listRangeStart) : null;
      let end = listRangeEnd ? endOfDay(listRangeEnd) : null;

      if (!start && end) start = startOfMonth(end);
      if (!end && start) end = endOfMonth(start);
      if (!start) start = startOfMonth(boundary);
      if (!end) end = endOfMonth(boundary);

      if (end < start) {
        const previousStart = start;
        start = startOfDay(end);
        end = endOfDay(previousStart);
      }

      return { start, end };
    };

    const getListPeriodLabel = () => {
      const { start, end } = getListRange();
      if (!start || !end) return "Lista";

      const sameYear = start.getFullYear() === end.getFullYear();
      const sameMonth = sameYear && start.getMonth() === end.getMonth();
      const isFullYear = sameYear
        && start.getMonth() === 0
        && start.getDate() === 1
        && end.getMonth() === 11
        && end.getDate() === 31;

      if (isFullYear) return String(start.getFullYear());
      if (sameMonth) {
        return capitalize(getFormatter(locale, { month: "long", year: "numeric" }).format(start));
      }
      if (sameYear) {
        const startLabel = capitalize(getFormatter(locale, { month: "short" }).format(start).replace(".", ""));
        const endLabel = capitalize(getFormatter(locale, { month: "short" }).format(end).replace(".", ""));
        return `${startLabel} – ${endLabel} ${start.getFullYear()}`;
      }

      const rangeFormatter = getFormatter(locale, { day: "numeric", month: "short", year: "numeric" });
      return `${rangeFormatter.format(start)} – ${rangeFormatter.format(end)}`;
    };

    const buildListDays = (visibleEvents) => {
      const { start, end } = getListRange();
      const rangeStart = startOfDay(start);
      const rangeEnd = endOfDay(end);
      const days = new Map();

      for (const event of visibleEvents) {
        if (!event.start) continue;
        const evtStart = event.start;
        const evtEnd = event.end || event.start;
        if (evtStart > rangeEnd || evtEnd < rangeStart) continue;

        let cursor = startOfDay(evtStart < rangeStart ? rangeStart : evtStart);
        const last = startOfDay(evtEnd > rangeEnd ? rangeEnd : evtEnd);
        while (cursor <= last) {
          const key = formatISODate(cursor);
          if (!days.has(key)) {
            days.set(key, { key, date: new Date(cursor.getTime()), items: [] });
          }
          days.get(key).items.push(event);
          cursor = addDays(cursor, 1);
        }
      }

      if (listShowAllDays) {
        let cursor = startOfDay(rangeStart);
        const last = startOfDay(rangeEnd);
        while (cursor <= last) {
          const key = formatISODate(cursor);
          if (!days.has(key)) {
            days.set(key, { key, date: new Date(cursor.getTime()), items: [] });
          }
          cursor = addDays(cursor, 1);
        }
      }

      const ordered = Array.from(days.values()).sort((a, b) => a.date - b.date);
      for (const day of ordered) {
        day.items.sort((a, b) => {
          if (a.allDay !== b.allDay) return a.allDay ? 1 : -1;
          return a.start - b.start || String(a.title).localeCompare(String(b.title), locale);
        });
      }

      return ordered;
    };

    const getListCategoryDescriptors = (visibleEvents) => {
      const descriptors = categories
        .filter((category) => activeCategories.has(category.name))
        .map((category) => ({
          name: category.name,
          label: category.label || category.name,
          color: category.color || colorOf(category.name),
          matches: (event) => event.category === category.name,
        }));

      if (visibleEvents.some((event) => !event.category)) {
        descriptors.push({
          name: "__uncategorized__",
          label: "Sem categoria",
          color: "var(--primary)",
          matches: (event) => !event.category,
        });
      }

      return descriptors;
    };

    const createListDateColumn = (date) => {
      const dateCol = el("div", { class: "calendar__list-date" });
      dateCol.appendChild(el("span", {
        class: "calendar__list-date-weekday",
        text: capitalize(getFormatter(locale, { weekday: "short" }).format(date).replace(".", "")),
      }));
      dateCol.appendChild(el("span", { class: "calendar__list-date-number", text: String(date.getDate()) }));
      return dateCol;
    };

    const createListEventItem = (event) => {
      const item = el("div", {
        class: "calendar__list-event",
        attrs: {
          role: "button",
          tabindex: "0",
          "data-calendar-event-id": event.id,
          "aria-label": event.title,
        },
        style: { "--cal-cat-color": event.color || colorOf(event.category) },
      });
      item.appendChild(el("div", { class: "calendar__list-event-title", text: event.title }));
      const time = formatTimeRange(event, locale);
      if (time) item.appendChild(el("div", { class: "calendar__list-event-time", text: time }));
      return item;
    };

    const createListEmptyState = (text = "Sem eventos") => el("div", {
      class: "calendar__list-empty-cell",
      text,
    });

    const autoScrollListToToday = ({ force = false } = {}) => {
      const todayRow = body.querySelector("[data-calendar-list-today='true']");
      if (!todayRow) return;

      const { start, end } = getListRange();
      const scrollKey = [
        mode,
        listVariant,
        listShowAllDays ? "all" : "events",
        formatISODate(start),
        formatISODate(end),
      ].join("|");

      if (!force && root.dataset.calendarListScrollKey === scrollKey) {
        return;
      }

      requestAnimationFrame(() => {
        todayRow.scrollIntoView({ block: "center", inline: "nearest" });
        root.dataset.calendarListScrollKey = scrollKey;
      });
    };

    const todayInListRange = () => {
      const { start, end } = getListRange();
      const today = startOfDay(new Date());
      return start && end && today >= start && today <= end;
    };

    const renderMonth = () => {
      const first = new Date(anchorDate.getFullYear(), anchorDate.getMonth(), 1);
      const gridStart = startOfWeek(first, firstWeekday);
      const today = startOfDay(new Date());

      setPeriodLabel(capitalize(getFormatter(locale, { month: "long", year: "numeric" }).format(first)));

      const wrap = el("div", { class: "calendar__month" });
      const weekdayHeader = el("div", { class: "calendar__month-weekdays" });
      for (let i = 0; i < 7; i += 1) {
        const sample = addDays(gridStart, i);
        const label = capitalize(getFormatter(locale, { weekday: "short" }).format(sample).replace(".", ""));
        weekdayHeader.appendChild(el("div", { class: "calendar__month-weekday", text: label }));
      }
      const scroll = el("div", { class: "calendar__month-grid-scroll" });
      scroll.appendChild(weekdayHeader);
      const gridWrap = el("div", { class: "calendar__month-grid" });
      const visible = filteredEvents();
      const maxLanes = isMobile() ? MAX_MONTH_LANES_MOBILE : MAX_MONTH_LANES_DESKTOP;

      for (let w = 0; w < 6; w += 1) {
        const weekStart = addDays(gridStart, w * 7);
        const weekEnd = endOfDay(addDays(weekStart, 6));

        const weekRow = el("div", { class: "calendar__week-row" });
        const dayCells = [];

        for (let d = 0; d < 7; d += 1) {
          const dayDate = addDays(weekStart, d);
          const isToday = isSameDay(dayDate, today);
          const isWeekend = dayDate.getDay() === 0 || dayDate.getDay() === 6;
          const isOtherMonth = !isSameMonth(dayDate, first);
          const cell = el("div", {
            class: [
              "calendar__day-cell",
              isOtherMonth ? "calendar__day-cell--other-month" : "",
              isWeekend ? "calendar__day-cell--weekend" : "",
              isToday ? "calendar__day-cell--today" : "",
            ].filter(Boolean).join(" "),
            attrs: {
              role: "gridcell",
              "aria-label": getFormatter(locale, { day: "numeric", month: "long", year: "numeric" }).format(dayDate),
              "data-calendar-day": formatISODate(dayDate),
            },
          });
          cell.appendChild(el("span", { class: "calendar__day-number", text: String(dayDate.getDate()) }));
          dayCells.push({ cell, dayDate, hiddenEvents: [] });
          weekRow.appendChild(cell);
        }

        // Build intervals for this week
        const intervals = [];
        for (const event of visible) {
          if (!eventOverlapsRange(event, weekStart, weekEnd)) continue;
          const evtStart = event.start;
          const evtEnd = event.end || event.start;
          const lo = Math.max(0, daysBetween(weekStart, evtStart));
          const hi = Math.min(6, daysBetween(weekStart, evtEnd));
          intervals.push({ event, lo, hi });
        }

        const { items } = assignLanes(intervals);

        const layer = el("div", { class: "calendar__multi-day-layer" });
        const cardHeight = 24;
        const gap = 2;

        for (const item of items) {
          if (item.lane >= maxLanes) {
            for (let c = item.lo; c <= item.hi; c += 1) {
              dayCells[c].hiddenEvents.push(item.event);
            }
            continue;
          }
          const continuedLeft = item.event.start < weekStart;
          const continuedRight = (item.event.end || item.event.start) > weekEnd;
          const card = createEventCard(item.event, {
            colorOf,
            multiDay: item.lo !== item.hi,
            continuedLeft,
            continuedRight,
            locale,
          });
          card.style.left = `calc(${(item.lo / 7) * 100}% + 2px)`;
          card.style.width = `calc(${((item.hi - item.lo + 1) / 7) * 100}% - 4px)`;
          card.style.top = `${item.lane * (cardHeight + gap)}px`;
          layer.appendChild(card);
        }

        weekRow.appendChild(layer);

        for (const { cell, dayDate, hiddenEvents } of dayCells) {
          if (hiddenEvents.length === 0) continue;

          const moreBtn = el("button", {
            class: "calendar__more-indicator",
            text: `+${hiddenEvents.length} mais`,
            attrs: {
              type: "button",
              "aria-haspopup": "true",
              "aria-expanded": "false",
              "data-calendar-more-toggle": "",
            },
          });

          const popover = el("div", { class: "calendar__more-popover", attrs: { role: "dialog" } });
          popover.appendChild(el("div", {
            class: "calendar__more-popover-day",
            text: getFormatter(locale, { day: "numeric", month: "long" }).format(dayDate),
          }));
          for (const ev of hiddenEvents) {
            popover.appendChild(createEventCard(ev, { colorOf, locale }));
          }

          moreBtn.addEventListener("click", (ev) => {
            ev.stopPropagation();
            const wasOpen = cell.dataset.morePopoverOpen === "true";
            // Fecha outros popovers abertos
            body.querySelectorAll('[data-more-popover-open="true"]').forEach((c) => {
              c.dataset.morePopoverOpen = "false";
              c.querySelector("[data-calendar-more-toggle]")?.setAttribute("aria-expanded", "false");
            });
            if (!wasOpen) {
              cell.dataset.morePopoverOpen = "true";
              moreBtn.setAttribute("aria-expanded", "true");
            }
          });

          cell.appendChild(moreBtn);
          cell.appendChild(popover);
        }

        gridWrap.appendChild(weekRow);
      }

      scroll.appendChild(gridWrap);
      wrap.appendChild(scroll);
      body.replaceChildren(wrap);
    };

    const renderWeek = () => {
      const weekStart = startOfWeek(anchorDate, firstWeekday);
      const weekEnd = endOfDay(addDays(weekStart, 6));
      const today = startOfDay(new Date());
      const useHours = weekShowHours;

      setPeriodLabel(
        `${getFormatter(locale, { day: "numeric", month: "short" }).format(weekStart)} – ${getFormatter(locale, { day: "numeric", month: "short", year: "numeric" }).format(addDays(weekStart, 6))}`
      );

      const wrap = el("div", { class: "calendar__week" + (useHours ? "" : " calendar__week--no-hours") });
      const scroll = el("div", { class: "calendar__week-scroll" });

      // Header (days)
      const header = el("div", { class: "calendar__week-header" + (useHours ? "" : " calendar__week-header--no-axis") });
      if (useHours) header.appendChild(el("div", { class: "calendar__week-axis-spacer" }));
      for (let d = 0; d < 7; d += 1) {
          const dayDate = addDays(weekStart, d);
          const isToday = isSameDay(dayDate, today);
          const isWeekend = isWeekendDate(dayDate);
        const cell = el("div", {
            class: [
              "calendar__week-day-header",
              isWeekend ? "calendar__week-day-header--weekend" : "calendar__week-day-header--weekday",
              isToday ? "calendar__week-day-header--today" : "",
            ].filter(Boolean).join(" "),
        });
        cell.appendChild(el("span", { class: "calendar__week-day-name", text: capitalize(getFormatter(locale, { weekday: "short" }).format(dayDate).replace(".", "")) }));
        cell.appendChild(el("span", { class: "calendar__week-day-number", text: String(dayDate.getDate()) }));
        header.appendChild(cell);
      }
      scroll.appendChild(header);

      const visible = filteredEvents();
      const inWeek = visible.filter((e) => eventOverlapsRange(e, weekStart, weekEnd));

      const allDayEvents = inWeek.filter((e) => e.allDay || !e.startHasTime || isMultiDayEvent(e));
      const timedEvents = inWeek.filter((e) => !e.allDay && e.startHasTime && !isMultiDayEvent(e));
      const spanningEvents = inWeek.filter((e) => isMultiDayEvent(e));
      const stackedEvents = inWeek.filter((e) => !isMultiDayEvent(e));

      // Faixa "Dia inteiro" só aparece no modo com horas, no topo do grid.
      if (useHours) {
        scroll.appendChild(createWeekAllDayBand({ weekStart, weekEnd, events: allDayEvents, colorOf, locale }));
      }

      if (useHours) {
        const grid = el("div", { class: "calendar__week-grid" });
        const pxPerMin = parseFloat(getComputedStyle(root).getPropertyValue("--cal-px-per-min")) || 0.8;
        const totalMinutes = (hourRange[1] - hourRange[0]) * 60;
        const totalHeight = totalMinutes * pxPerMin;

        const hoursCol = el("div", {
          class: "calendar__week-hours",
          style: { height: `${totalHeight}px` },
        });
        for (let h = hourRange[0]; h < hourRange[1]; h += 1) {
          hoursCol.appendChild(el("div", {
            class: "calendar__week-hour",
            text: `${String(h).padStart(2, "0")}:00`,
          }));
        }
        grid.appendChild(hoursCol);

        for (let d = 0; d < 7; d += 1) {
          const dayDate = addDays(weekStart, d);
          const isToday = isSameDay(dayDate, today);
          const isWeekend = isWeekendDate(dayDate);
          const dayCol = el("div", {
            class: [
              "calendar__week-day-column",
              isWeekend ? "calendar__week-day-column--weekend" : "calendar__week-day-column--weekday",
              isToday ? "calendar__week-day-column--today" : "",
            ].filter(Boolean).join(" "),
            style: { height: `${totalHeight}px` },
          });
          for (let h = hourRange[0] + 1; h < hourRange[1]; h += 1) {
            dayCol.appendChild(el("div", {
              class: "calendar__week-hour-line",
              style: { top: `${(h - hourRange[0]) * 60 * pxPerMin}px` },
            }));
          }

          // Events on this day (timed)
          const dayStart = startOfDay(dayDate);
          const dayEnd = endOfDay(dayDate);
          const dayEvents = [];
          for (const event of timedEvents) {
            const evtStart = event.start;
            const evtEnd = event.end && event.endHasTime ? event.end : new Date(evtStart.getTime() + DEFAULT_EVENT_DURATION_MIN * 60000);
            if (evtStart > dayEnd || evtEnd < dayStart) continue;
            // Clip to day
            const clipStart = evtStart < dayStart ? dayStart : evtStart;
            const clipEnd = evtEnd > dayEnd ? dayEnd : evtEnd;
            const startMin = (clipStart - dayStart) / 60000;
            const endMin = (clipEnd - dayStart) / 60000;
            const visibleStart = Math.max(startMin, hourRange[0] * 60);
            const visibleEnd = Math.min(endMin, hourRange[1] * 60);
            if (visibleEnd <= visibleStart) continue;
            dayEvents.push({
              event,
              lo: visibleStart,
              hi: visibleEnd,
              continuedLeft: evtStart < dayStart,
              continuedRight: evtEnd > dayEnd,
            });
          }

          const { items, laneCount } = assignLanes(dayEvents);
          for (const item of items) {
            const top = (item.lo - hourRange[0] * 60) * pxPerMin;
            const height = Math.max(18, (item.hi - item.lo) * pxPerMin);
            const lanes = laneCount || 1;
            const card = createEventCard(item.event, {
              colorOf,
              locale,
              showTime: true,
              continuedLeft: item.continuedLeft,
              continuedRight: item.continuedRight,
            });
            card.style.top = `${top}px`;
            card.style.height = `${height}px`;
            card.style.left = `calc(${(item.lane / lanes) * 100}% + 1px)`;
            card.style.width = `calc(${100 / lanes}% - 2px)`;
            dayCol.appendChild(card);
          }

          grid.appendChild(dayCol);
        }
        scroll.appendChild(grid);
      } else {
        // Modo sem horas: TODOS os eventos (all-day e com hora) ficam na pilha
        // do dia, ordenados por horário (eventos com hora primeiro, depois all-day).
        if (spanningEvents.length) {
          scroll.appendChild(createWeekAllDayBand({
            weekStart,
            weekEnd,
            events: spanningEvents,
            colorOf,
            locale,
            showAxisLabel: false,
          }));
        }

        const stacked = el("div", { class: "calendar__week-stacked" });
        for (let d = 0; d < 7; d += 1) {
          const dayDate = addDays(weekStart, d);
          const dayStart = startOfDay(dayDate);
          const dayEnd = endOfDay(dayDate);
          const isToday = isSameDay(dayDate, today);
          const isWeekend = isWeekendDate(dayDate);
          const cell = el("div", {
            class: [
              "calendar__week-stacked-cell",
              isWeekend ? "calendar__week-stacked-cell--weekend" : "calendar__week-stacked-cell--weekday",
              isToday ? "calendar__week-stacked-cell--today" : "",
            ].filter(Boolean).join(" "),
          });

          const dayItems = stackedEvents
            .filter((event) => {
              const evtEnd = event.end || event.start;
              return event.start <= dayEnd && evtEnd >= dayStart;
            })
            .sort((a, b) => {
              if (a.allDay !== b.allDay) return a.allDay ? 1 : -1;
              return a.start - b.start;
            });

          for (const event of dayItems) {
            const evtStart = event.start;
            const evtEnd = event.end || event.start;
            const continuedLeft = evtStart < dayStart;
            const continuedRight = evtEnd > dayEnd;
            cell.appendChild(createEventCard(event, {
              colorOf,
              locale,
              showTime: !event.allDay,
              continuedLeft,
              continuedRight,
            }));
          }
          stacked.appendChild(cell);
        }
        scroll.appendChild(stacked);
      }

      wrap.appendChild(scroll);
      body.replaceChildren(wrap);
    };

    const renderListDefault = (days, today) => {
      if (days.length === 0) {
        body.replaceChildren(el("div", { class: "calendar__empty", text: config.emptyMessage || "Nenhum evento." }));
        return;
      }

      const wrap = el("div", { class: "calendar__list" });
      let lastMonthKey = null;
      let monthBlock = null;

      for (const day of days) {
        const { date, items } = day;
        const monthKey = `${date.getFullYear()}-${date.getMonth()}`;
        if (monthKey !== lastMonthKey) {
          monthBlock = el("div", { class: "calendar__list-month" });
          monthBlock.appendChild(el("div", {
            class: "calendar__list-month-header",
            text: capitalize(getFormatter(locale, { month: "long", year: "numeric" }).format(date)),
          }));
          wrap.appendChild(monthBlock);
          lastMonthKey = monthKey;
        }

        const isToday = isSameDay(date, today);
        const isWeekend = isWeekendDate(date);
        const dayBlock = el("div", {
          class: [
            "calendar__list-day",
            isWeekend ? "calendar__list-day--weekend" : "calendar__list-day--weekday",
            isToday ? "calendar__list-day--today" : "",
          ].filter(Boolean).join(" "),
          attrs: {
            "data-calendar-day": formatISODate(date),
            "data-calendar-list-today": isToday ? "true" : null,
          },
        });
        dayBlock.appendChild(createListDateColumn(date));

        const eventsCol = el("div", { class: "calendar__list-events" });
        if (items.length === 0) {
          eventsCol.appendChild(createListEmptyState());
        } else {
          for (const event of items) eventsCol.appendChild(createListEventItem(event));
        }

        dayBlock.appendChild(eventsCol);
        monthBlock.appendChild(dayBlock);
      }

      body.replaceChildren(wrap);
    };

    const renderListByCategory = (days, today, visibleEvents) => {
      const descriptors = getListCategoryDescriptors(visibleEvents);
      if (descriptors.length === 0) {
        renderListDefault(days, today);
        return;
      }

      const wrap = el("div", { class: "calendar__list calendar__list--by-category" });
      wrap.style.setProperty("--cal-list-category-count", String(descriptors.length));

      let lastMonthKey = null;
      let monthBlock = null;

      for (const day of days) {
        const { date, items } = day;
        const monthKey = `${date.getFullYear()}-${date.getMonth()}`;
        if (monthKey !== lastMonthKey) {
          monthBlock = el("div", { class: "calendar__list-month calendar__list-month--by-category" });
          monthBlock.appendChild(el("div", {
            class: "calendar__list-month-header",
            text: capitalize(getFormatter(locale, { month: "long", year: "numeric" }).format(date)),
          }));

          const headerRow = el("div", { class: "calendar__list-category-header-row" });
          headerRow.appendChild(el("div", {
            class: "calendar__list-category-head-spacer",
            text: "Data",
          }));
          for (const descriptor of descriptors) {
            headerRow.appendChild(el("div", {
              class: "calendar__list-category-header",
              text: descriptor.label,
              style: { "--cal-cat-color": descriptor.color },
            }));
          }
          monthBlock.appendChild(headerRow);

          wrap.appendChild(monthBlock);
          lastMonthKey = monthKey;
        }

        const isToday = isSameDay(date, today);
        const isWeekend = isWeekendDate(date);
        const row = el("div", {
          class: [
            "calendar__list-category-row",
            isWeekend ? "calendar__list-category-row--weekend" : "calendar__list-category-row--weekday",
            isToday ? "calendar__list-category-row--today" : "",
          ].filter(Boolean).join(" "),
          attrs: {
            "data-calendar-day": formatISODate(date),
            "data-calendar-list-today": isToday ? "true" : null,
          },
        });
        row.appendChild(createListDateColumn(date));

        for (const descriptor of descriptors) {
          const cell = el("div", {
            class: "calendar__list-category-cell",
            attrs: { "data-category-label": descriptor.label },
            style: { "--cal-cat-color": descriptor.color },
          });
          const categoryItems = items.filter((event) => descriptor.matches(event));
          if (categoryItems.length === 0) {
            cell.appendChild(createListEmptyState("—"));
          } else {
            for (const event of categoryItems) cell.appendChild(createListEventItem(event));
          }
          row.appendChild(cell);
        }

        monthBlock.appendChild(row);
      }

      body.replaceChildren(wrap);
    };

    const renderList = () => {
      const visible = filteredEvents()
        .slice()
        .sort((a, b) => a.start - b.start || String(a.title).localeCompare(String(b.title), locale));
      const days = buildListDays(visible);
      const today = startOfDay(new Date());

      setPeriodLabel(getListPeriodLabel());

      if (days.length === 0) {
        body.replaceChildren(el("div", { class: "calendar__empty", text: config.emptyMessage || "Nenhum evento." }));
        return;
      }

      if (listVariant === "category") renderListByCategory(days, today, visible);
      else renderListDefault(days, today);

      autoScrollListToToday();
    };

    const render = () => {
      root.dataset.calendarMode = mode;
      body.dataset.calendarMode = mode;
      if (mode !== "list") {
        delete root.dataset.calendarListScrollKey;
      }

      // Update toggle pressed states
      if (modeToggle) {
        modeToggle.querySelectorAll("[data-calendar-mode]").forEach((btn) => {
          const pressed = btn.dataset.calendarMode === mode;
          btn.setAttribute("aria-pressed", pressed ? "true" : "false");
          btn.setAttribute("aria-checked", pressed ? "true" : "false");
        });
      }

      // Show/hide week-hours toggle (only relevant in week mode)
      if (weekHoursToggle) {
        weekHoursToggle.hidden = mode !== "week";
        if (weekHoursCheckbox) weekHoursCheckbox.checked = weekShowHours;
      }

      if (listControls) {
        listControls.hidden = mode !== "list";
      }

      if (listVariantToggle) {
        listVariantToggle.querySelectorAll("[data-calendar-list-variant]").forEach((btn) => {
          const pressed = btn.dataset.calendarListVariant === listVariant;
          btn.setAttribute("aria-pressed", pressed ? "true" : "false");
          btn.setAttribute("aria-checked", pressed ? "true" : "false");
        });
      }

      if (listShowAllDaysCheckbox) {
        listShowAllDaysCheckbox.checked = listShowAllDays;
      }

      // Em list mode, prev/next não fazem sentido — só "Hoje" continua visível
      // (e desabilitado se hoje estiver fora do range exibido).
      if (navPrev) navPrev.style.display = mode === "list" ? "none" : "";
      if (navNext) navNext.style.display = mode === "list" ? "none" : "";
      if (navToday && mode === "list") {
        const enabled = todayInListRange();
        navToday.disabled = !enabled;
        navToday.setAttribute("aria-disabled", enabled ? "false" : "true");
      } else if (navToday) {
        navToday.disabled = false;
        navToday.removeAttribute("aria-disabled");
      }

      if (mode === "month") renderMonth();
      else if (mode === "week") renderWeek();
      else renderList();
    };

    // -------- Wiring ----------------------------------------------------

    if (modeToggle) {
      modeToggle.addEventListener("click", (event) => {
        const btn = event.target.closest("[data-calendar-mode]");
        if (!btn) return;
        const next = btn.dataset.calendarMode;
        if (!allowedModes.includes(next) || next === mode) return;
        mode = next;
        render();
      });
    }

    if (listVariantToggle) {
      listVariantToggle.addEventListener("click", (event) => {
        const btn = event.target.closest("[data-calendar-list-variant]");
        if (!btn) return;
        const next = btn.dataset.calendarListVariant;
        if (!allowedListVariants.includes(next) || next === listVariant) return;
        listVariant = next;
        render();
      });
    }

    const navBy = (direction) => {
      if (mode === "month") anchorDate = addMonths(anchorDate, direction);
      else if (mode === "week") anchorDate = addDays(anchorDate, direction * 7);
      else anchorDate = addMonths(anchorDate, direction);
      render();
    };

    if (navPrev) navPrev.addEventListener("click", () => navBy(-1));
    if (navNext) navNext.addEventListener("click", () => navBy(1));
    if (navToday) {
      navToday.addEventListener("click", () => {
        if (mode === "list") {
          if (!todayInListRange()) return;
          autoScrollListToToday({ force: true });
          return;
        }
        anchorDate = startOfDay(new Date());
        render();
      });
    }

    // Filters
    const updateFiltersCount = () => {
      if (!filtersCount) return;
      const total = categories.length;
      const active = activeCategories.size;
      filtersCount.textContent = active === total ? "" : ` (${active}/${total})`;
    };

    if (filtersToggle && filtersWrap) {
      filtersToggle.addEventListener("click", (event) => {
        event.stopPropagation();
        const open = filtersWrap.dataset.open === "true";
        filtersWrap.dataset.open = open ? "false" : "true";
        filtersToggle.setAttribute("aria-expanded", open ? "false" : "true");
      });
      document.addEventListener("click", (event) => {
        if (!filtersWrap.contains(event.target)) {
          filtersWrap.dataset.open = "false";
          filtersToggle.setAttribute("aria-expanded", "false");
        }
      });
    }

    root.querySelectorAll("[data-calendar-filter]").forEach((cb) => {
      cb.addEventListener("change", () => {
        if (cb.checked) activeCategories.add(cb.value);
        else activeCategories.delete(cb.value);
        updateFiltersCount();
        render();
      });
    });

    const allBtn = root.querySelector("[data-calendar-filters-all]");
    const noneBtn = root.querySelector("[data-calendar-filters-none]");
    if (allBtn) {
      allBtn.addEventListener("click", () => {
        for (const cat of categories) activeCategories.add(cat.name);
        root.querySelectorAll("[data-calendar-filter]").forEach((cb) => { cb.checked = true; });
        updateFiltersCount();
        render();
      });
    }
    if (noneBtn) {
      noneBtn.addEventListener("click", () => {
        activeCategories.clear();
        root.querySelectorAll("[data-calendar-filter]").forEach((cb) => { cb.checked = false; });
        updateFiltersCount();
        render();
      });
    }

    if (weekHoursCheckbox) {
      weekHoursCheckbox.addEventListener("change", () => {
        weekShowHours = weekHoursCheckbox.checked;
        render();
      });
    }

    if (listShowAllDaysCheckbox) {
      listShowAllDaysCheckbox.addEventListener("change", () => {
        listShowAllDays = listShowAllDaysCheckbox.checked;
        render();
      });
    }

    const closeAllMorePopovers = () => {
      body.querySelectorAll('[data-more-popover-open="true"]').forEach((cell) => {
        cell.dataset.morePopoverOpen = "false";
        cell.querySelector("[data-calendar-more-toggle]")?.setAttribute("aria-expanded", "false");
      });
    };

    // Click fora fecha qualquer popover "+N" aberto. O botão "+N" usa
    // stopPropagation para que clicar nele NÃO acione este listener.
    document.addEventListener("click", closeAllMorePopovers);

    // Click delegation: dispatch CustomEvent
    body.addEventListener("click", (event) => {
      const card = event.target.closest("[data-calendar-event-id]");
      if (!card) return;
      const eventId = card.getAttribute("data-calendar-event-id");
      const found = events.find((e) => String(e.id) === String(eventId));
      if (!found) return;
      root.dispatchEvent(new CustomEvent("gris:calendar:event-click", {
        bubbles: true,
        detail: {
          id: found.id,
          title: found.title,
          start: found.raw.start,
          end: found.raw.end,
          all_day: found.allDay,
          category: found.category,
          data: found.data,
        },
      }));
    });

    body.addEventListener("keydown", (event) => {
      if (event.key !== "Enter" && event.key !== " ") return;
      const card = event.target.closest("[data-calendar-event-id]");
      if (!card) return;
      event.preventDefault();
      card.click();
    });

    // Re-render on viewport breakpoint changes (mobile lane count etc.)
    let lastIsMobile = isMobile();
    window.addEventListener("resize", () => {
      const nowMobile = isMobile();
      if (nowMobile !== lastIsMobile) {
        lastIsMobile = nowMobile;
        render();
      }
    });

    // -------- Public API on root element -------------------------------

    Object.defineProperty(root, "events", {
      configurable: true,
      get() { return events.map((e) => e.raw); },
      set(value) {
        events = (value || []).map(normalizeEvent);
        render();
      },
    });

    Object.defineProperty(root, "activeCategories", {
      configurable: true,
      get() { return Array.from(activeCategories); },
      set(value) {
        activeCategories.clear();
        for (const name of value || []) activeCategories.add(name);
        root.querySelectorAll("[data-calendar-filter]").forEach((cb) => {
          cb.checked = activeCategories.has(cb.value);
        });
        updateFiltersCount();
        render();
      },
    });

    root.setMode = (next) => {
      if (!allowedModes.includes(next)) return;
      mode = next;
      render();
    };

    root.setListVariant = (next) => {
      if (!allowedListVariants.includes(next)) return;
      listVariant = next;
      render();
    };

    root.setListShowAllDays = (next) => {
      listShowAllDays = !!next;
      render();
    };

    root.setListRange = (startIso, endIso) => {
      listRangeStart = startIso ? parseISO(startIso) : null;
      listRangeEnd = endIso ? parseISO(endIso) : null;

      if (listRangeStart) listRangeStart = startOfDay(listRangeStart);
      if (listRangeEnd) listRangeEnd = endOfDay(listRangeEnd);
      if (listRangeStart && listRangeEnd && listRangeEnd < listRangeStart) {
        const previousStart = listRangeStart;
        listRangeStart = startOfDay(listRangeEnd);
        listRangeEnd = endOfDay(previousStart);
      }

      render();
    };

    root.setActiveCategories = (names) => {
      root.activeCategories = names;
    };

    root.goToDate = (iso) => {
      const d = parseISO(iso);
      if (d) {
        anchorDate = startOfDay(d);
        render();
      }
    };

    root.refresh = render;

    // Initial render
    updateFiltersCount();
    render();
    root.dataset.calendarInitialized = "true";
    root.dispatchEvent(new CustomEvent("basecoat:initialized", { bubbles: true }));
  };

  // -------- Auto-init -------------------------------------------------

  const initAll = () => {
    document.querySelectorAll("[data-calendar]").forEach(initCalendar);
  };

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", initAll, { once: true });
  } else {
    initAll();
  }

  document.addEventListener("gris:design-system:init", initAll);

  // Observe future DOM insertions to auto-init dynamically added calendars.
  if (typeof MutationObserver !== "undefined") {
    const observer = new MutationObserver((mutations) => {
      for (const m of mutations) {
        for (const node of m.addedNodes) {
          if (!(node instanceof Element)) continue;
          if (node.matches?.("[data-calendar]")) initCalendar(node);
          node.querySelectorAll?.("[data-calendar]").forEach(initCalendar);
        }
      }
    });
    if (document.body) observer.observe(document.body, { childList: true, subtree: true });
    else document.addEventListener("DOMContentLoaded", () => {
      observer.observe(document.body, { childList: true, subtree: true });
    }, { once: true });
  }
})();
