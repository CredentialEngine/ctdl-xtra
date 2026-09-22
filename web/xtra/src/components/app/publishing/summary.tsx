import ArrowForwardIcon from "@mui/icons-material/ArrowForward";
import FactCheckIcon from "@mui/icons-material/FactCheck";
import PlayArrowIcon from "@mui/icons-material/PlayArrow";
import { Box, Button, Card, CardContent, Typography } from "@mui/material";
import Link from "@/components/ui/route-link";

const steps = [
    "Confirm that the source has the discovered pages you intend to publish.",
    "Choose the strategy and project context for the publishing run.",
    "Start the ETL run and follow its progress through extraction, transformation, and publish-ready output.",
    "Open a completed or failed run to inspect its status and details before continuing.",
];

export default function PublishingSummary() {
    return (
        <Box className="space-y-6" sx={{ color: "text.primary" }}>
            <Box sx={{ maxWidth: 900 }}>
                <Typography variant="h1" component="h1">
                    Publishing
                </Typography>
                <Typography
                    color="text.secondary"
                    sx={{ mt: 1, maxWidth: 780 }}
                >
                    Publishing is the final operational stage. Use this area
                    when a source is ready to move through ETL and into its
                    publishing destination.
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
                            Before you publish
                        </Typography>
                        <Box
                            component="ol"
                            sx={{ m: 0, pl: 2.5, display: "grid", gap: 1.5 }}
                        >
                            {steps.map((step) => (
                                <Typography
                                    component="li"
                                    color="text.secondary"
                                    key={step}
                                >
                                    {step}
                                </Typography>
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
                            href="/publishing/runs"
                            variant="contained"
                            startIcon={<FactCheckIcon />}
                            endIcon={<ArrowForwardIcon />}
                        >
                            ETL Runs
                        </Button>
                        <Button
                            component={Link}
                            href="/publishing/new"
                            variant="outlined"
                            startIcon={<PlayArrowIcon />}
                        >
                            Start ETL run
                        </Button>
                    </CardContent>
                </Card>
            </Box>
        </Box>
    );
}
