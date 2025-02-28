UPDATE crawl_pages SET page_type = 'DETAIL' WHERE page_type = 'COURSE_DETAIL_PAGE';--> statement-breakpoint
UPDATE crawl_pages SET page_type = 'DETAIL_LINKS' WHERE page_type = 'COURSE_LINKS_PAGE';--> statement-breakpoint
UPDATE crawl_pages SET page_type = 'CATEGORY_LINKS' WHERE page_type = 'CATEGORY_LINKS_PAGE';
