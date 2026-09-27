import ArrowForwardIcon from "@mui/icons-material/ArrowForward";
import CloudDownloadIcon from "@mui/icons-material/CloudDownload";
import LanguageIcon from "@mui/icons-material/Language";
import AddIcon from "@mui/icons-material/Add";
import { Box, Button, Card, CardContent, Typography } from "@mui/material";
import Link from "@/components/ui/route-link";

const steps = [
    {
        title: "1. Add and organize sources",
        text: "Create a source for a public website, associate it with the right organization, and add tags that make the source easy to find later.",
    },
    {
        title: "2. Run a crawl",
        text: "Open a source and start a crawl to collect candidate pages. Crawl Runs gives you one place to monitor the crawl history and status.",
    },
    {
        title: "3. Review discovered pages",
        text: "Open a completed crawl when you are ready to review discovery results and decide which pages should continue through the pipeline.",
    },
];

export default function SourcesSummary() {
    return (
        <Box className="space-y-6" sx={{ color: "text.primary" }}>
            <Box sx={{ maxWidth: 900 }}>
                <Typography variant="h1" component="h1">
                    Sources
                </Typography>
                <Typography
                    color="text.secondary"
                    sx={{ mt: 1, maxWidth: 760 }}
                >
                    Start here when you are bringing a website into xTRA. A
                    source is the starting point for crawling, discovery,
                    benchmarking, and publishing.
                </Typography>
            </Box>

            <Box
                sx={{
                    display: "grid",
                    gridTemplateColumns: { xs: "1fr", lg: "1.15fr 0.85fr" },
                    gap: 2,
                }}
            >
                <Card>
                    <CardContent sx={{ p: 3 }}>
                        <Typography variant="h2" component="h2" sx={{ mb: 2 }}>
                            Recommended workflow
                        </Typography>
                        <Box sx={{ display: "grid", gap: 2.25 }}>
                            {steps.map((step) => (
                                <Box key={step.title}>
                                    <Typography sx={{ fontWeight: 700 }}>
                                        {step.title}
                                    </Typography>
                                    <Typography
                                        color="text.secondary"
                                        sx={{ mt: 0.5 }}
                                    >
                                        {step.text}
                                    </Typography>
                                </Box>
                            ))}
                        </Box>
                    </CardContent>
                </Card>

                <Card>
                    <CardContent sx={{ p: 3, display: "grid", gap: 2 }}>
                        <Typography variant="h2" component="h2">
                            Go to
                        </Typography>
                        <Button
                            component={Link}
                            href="/sources/all"
                            variant="contained"
                            startIcon={<LanguageIcon />}
                            endIcon={<ArrowForwardIcon />}
                        >
                            All Sources
                        </Button>
                        <Button
                            component={Link}
                            href="/crawls"
                            variant="outlined"
                            startIcon={<CloudDownloadIcon />}
                            endIcon={<ArrowForwardIcon />}
                        >
                            Crawl Runs
                        </Button>
                        <Button
                            component={Link}
                            href="/sources/new"
                            variant="outlined"
                            startIcon={<AddIcon />}
                        >
                            Add source
                        </Button>
                    </CardContent>
                </Card>
            </Box>
        </Box>
    );
}
