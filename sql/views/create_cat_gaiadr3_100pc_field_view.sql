-- Public Gaia DR3 100 pc field view for the MOCAviz Gaia CMD explorer.
--
-- Run this with a privileged account that can create views in `mocadb`
-- and can read `mocadb_private_tables`.`pcat_gaiadr3_100pc_field`.

USE `mocadb`;

CREATE OR REPLACE
    ALGORITHM = MERGE
    SQL SECURITY DEFINER
VIEW `cat_gaiadr3_100pc_field` AS
SELECT *
FROM `mocadb_private_tables`.`pcat_gaiadr3_100pc_field`;

-- Optional verification after creation:
-- SELECT COUNT(*) AS n_rows
-- FROM `mocadb`.`cat_gaiadr3_100pc_field`;
