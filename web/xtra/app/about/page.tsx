import { Box, Card, CardContent, Typography } from "@mui/material";

export default function AboutPage() {
    return (
        <Box
            sx={{
                maxWidth: 960,
                mx: "auto",
                py: { xs: 2, md: 4 },
                color: "text.primary",
            }}
        >
            <Card
                sx={{
                    bgcolor: "background.paper",
                    color: "text.primary",
                    borderColor: "divider",
                    boxShadow: "none",
                }}
            >
                <CardContent sx={{ p: { xs: 3, md: 4 } }}>
                    <Typography variant="h1" component="h1" sx={{ mb: 2 }}>
                        About CTDL xTRA
                    </Typography>
                    <Typography
                        color="text.secondary"
                        sx={{ lineHeight: 1.7, maxWidth: 760 }}
                    >
                        CTDL xTRA is a pipeline control plane for managing
                        public website sources, crawling and discovering useful
                        pages, validating pipeline behavior with benchmarks, and
                        publishing complete sources to projects.
                    </Typography>
                </CardContent>
            </Card>
        </Box>
    );
}
