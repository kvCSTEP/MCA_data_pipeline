SELECT
    '0-3' AS range,
    COUNT(*) AS count,
    SUM(system_size) / 1000 AS total_size_in_kW
FROM mcapanels.mysore_polygons
WHERE system_size >= 0 AND system_size < 3 AND cuf >= 0.16

UNION ALL

SELECT
    '3-10' AS range,
    COUNT(*) AS count,
    SUM(system_size) / 1000 AS total_size_in_kW
FROM mcapanels.mysore_polygons
WHERE system_size >= 3 AND system_size < 10 AND cuf >= 0.16

UNION ALL

SELECT
    '10-50' AS range,
    COUNT(*) AS count,
    SUM(system_size) / 1000 AS total_size_in_kW
FROM mcapanels.mysore_polygons
WHERE system_size >= 10 AND system_size < 50 AND cuf >= 0.16

UNION ALL

SELECT
    '50-2000' AS range,
    COUNT(*) AS count,
    SUM(system_size) / 1000 AS total_size_in_kW
FROM mcapanels.mysore_polygons
WHERE system_size >= 50 AND system_size < 2000 AND cuf >= 0.16;

---------------------------------------------------------------------

CREATE OR REPLACE FUNCTION get_system_size_report(location_name text)
RETURNS TABLE (
    range text,
    count bigint,
    total_size_in_kw numeric
) AS $$
BEGIN
    RETURN QUERY EXECUTE FORMAT($q$
        SELECT
            range_name AS range,
            COUNT(*) AS count,
            COALESCE(SUM(system_size) / 1000, 0) AS total_size_in_kw
        FROM (
            VALUES
                ('0-3', 0, 3),
                ('3-10', 3, 10),
                ('10-50', 10, 50),
                ('50-2000', 50, 2000)
        ) AS ranges(range_name, min_size, max_size)
        LEFT JOIN mcapanels.%I_polygons p ON
            p.system_size >= min_size
            AND p.system_size < max_size
            AND p.cuf >= 0.16
        GROUP BY range_name, min_size
        ORDER BY min_size
    $q$, location_name);
END;
$$ LANGUAGE plpgsql;

-- To run the report, execute:
SELECT * FROM get_system_size_report('jabalpur');