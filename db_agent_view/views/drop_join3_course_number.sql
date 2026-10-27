-- Restores db_agent_view to the baseline state of the join3_course_number experiment.
-- av_catalog only describes this view so far; drop it too so the baseline schema has no av_ objects.
DROP VIEW IF EXISTS av_library_offering_course;
DROP TABLE IF EXISTS av_catalog;
