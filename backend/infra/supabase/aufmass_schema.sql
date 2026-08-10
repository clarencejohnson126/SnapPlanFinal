-- SnapPlan Aufmaß — Persistenz für Schicht 2 und 3.
--
-- Läuft im Supabase-Projekt BarberBuddyGPT (eoahpwciwttfavzpqfnz) mit, weil der
-- Free-Plan nur zwei aktive Projekte erlaubt. Deshalb trägt jede Tabelle den
-- Präfix snapplan_ — sie teilen sich die Datenbank mit einem fremden Produkt
-- und dürfen dessen Namensraum nicht belegen.
--
-- Ersetzt den prozesslokalen Speicher in app/api/aufmass.py. Der hält Ergebnisse
-- nur bis zum nächsten Neustart, was auf Render bedeutet: ein Kaltstart löscht
-- jedes laufende Aufmaß.

-- ----------------------------------------------------------------- Jobs

create table if not exists public.snapplan_aufmass_jobs (
    id                uuid primary key default gen_random_uuid(),
    document_id       text not null,
    trade             text not null,
    ruleset_id        text,
    ruleset_version   text,

    -- Maßstab, mit dem gerechnet wurde. Ein Aufmaß ohne bestätigten Maßstab ist
    -- nicht abrechnungsfähig, deshalb wird beides festgehalten.
    scale_denominator integer,
    scale_confirmed   boolean not null default false,

    -- Warnungen der Extraktion, die alle Positionen betreffen.
    warnings          jsonb not null default '[]'::jsonb,

    -- Ablageort des Plans, damit der Prüf-Screen Seiten rendern kann.
    plan_storage_path text,

    created_by        uuid references auth.users(id) on delete set null,
    created_at        timestamptz not null default now(),
    updated_at        timestamptz not null default now()
);

comment on table public.snapplan_aufmass_jobs is
    'Ein Aufmaß-Lauf: ein Plan, ein Gewerk, ein Regelwerkstand.';

create index if not exists snapplan_aufmass_jobs_created_by_idx
    on public.snapplan_aufmass_jobs (created_by, created_at desc);

-- ------------------------------------------------------------ Positionen

create table if not exists public.snapplan_aufmass_positions (
    id              uuid primary key default gen_random_uuid(),
    job_id          uuid not null
                      references public.snapplan_aufmass_jobs(id) on delete cascade,

    -- Fachliche Kennung aus der Domäne, für Zuordnung nach einem Neuberechnen.
    position_id     text not null,

    designation     text not null,
    quantity        numeric(14,3) not null,
    unit            text not null,
    kind            text not null,

    -- Der geometrische Wert vor Anwendung der Abrechnungsregeln. Erlaubt die
    -- Anzeige "geometrisch 55,22 → abrechenbar 51,22" und belegt, dass das
    -- Regelwerk überhaupt gegriffen hat.
    raw_quantity    numeric(14,3),

    -- Der Rechenweg. Das ist der eigentliche Wert des Datensatzes: eine Menge
    -- ohne nachvollziehbare Herleitung wird vom Prüfer zurückgewiesen.
    calculation     jsonb not null default '[]'::jsonb,

    -- Belege mit Fundstelle im Plan (Seite, Geometrie in PDF-Punkten, Rohtext).
    evidence        jsonb not null default '[]'::jsonb,

    warnings        jsonb not null default '[]'::jsonb,

    -- auto | reviewed | corrected | manual. Nur die letzten drei sind
    -- exportierbar — hier hängt die Haftung.
    status          text not null default 'auto',
    reviewed_by     text,
    reviewed_at     timestamptz,

    room_id         text,
    room_label      text,
    lv_position     text,

    created_at      timestamptz not null default now(),

    constraint snapplan_aufmass_positions_status_check
        check (status in ('auto', 'reviewed', 'corrected', 'manual')),
    constraint snapplan_aufmass_positions_unique_per_job
        unique (job_id, position_id)
);

comment on column public.snapplan_aufmass_positions.status is
    'auto = Maschinenvorschlag, nicht exportierbar. reviewed/corrected/manual = ein Mensch hat die Verantwortung übernommen.';

create index if not exists snapplan_aufmass_positions_job_idx
    on public.snapplan_aufmass_positions (job_id);

create index if not exists snapplan_aufmass_positions_open_idx
    on public.snapplan_aufmass_positions (job_id)
    where status = 'auto';

-- ------------------------------------------------------------------- RLS
--
-- Aufmaße enthalten Kundendaten aus fremden Bauprojekten. Ohne RLS könnte jeder
-- angemeldete Nutzer des mitbenutzten Projekts sie lesen.

alter table public.snapplan_aufmass_jobs enable row level security;
alter table public.snapplan_aufmass_positions enable row level security;

drop policy if exists snapplan_jobs_owner on public.snapplan_aufmass_jobs;
create policy snapplan_jobs_owner
    on public.snapplan_aufmass_jobs
    for all
    using (created_by = auth.uid())
    with check (created_by = auth.uid());

drop policy if exists snapplan_positions_owner on public.snapplan_aufmass_positions;
create policy snapplan_positions_owner
    on public.snapplan_aufmass_positions
    for all
    using (
        exists (
            select 1 from public.snapplan_aufmass_jobs j
            where j.id = job_id and j.created_by = auth.uid()
        )
    )
    with check (
        exists (
            select 1 from public.snapplan_aufmass_jobs j
            where j.id = job_id and j.created_by = auth.uid()
        )
    );

-- -------------------------------------------------------- updated_at pflegen

create or replace function public.snapplan_touch_updated_at()
returns trigger
language plpgsql
as $$
begin
    new.updated_at = now();
    return new;
end;
$$;

drop trigger if exists snapplan_aufmass_jobs_touch on public.snapplan_aufmass_jobs;
create trigger snapplan_aufmass_jobs_touch
    before update on public.snapplan_aufmass_jobs
    for each row execute function public.snapplan_touch_updated_at();
