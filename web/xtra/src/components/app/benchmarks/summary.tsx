import ArrowForwardIcon from "@mui/icons-material/ArrowForward";
import WorkspacesIcon from "@mui/icons-material/SpaceDashboard";
import RunsIcon from "@mui/icons-material/FactCheck";
import StrategiesIcon from "@mui/icons-material/AccountTree";
import { Box, Button, Card, CardContent, Typography } from "@mui/material";
import Link from "@/components/ui/route-link";

const guidance = [
    {
        title: "Workspaces",
        text: "Use a workspace to review benchmark pages for a source and maintain the examples that represent the expected result.",
    },
    {
        title: "Strategies",
        text: "Use strategies to define the benchmark behavior you want to exercise before a strategy is used more broadly.",
    },
    {
        title: "Runs",
        text: "Run benchmarks, inspect outcomes, and use the results to understand where a strategy or source needs attention.",
    },
];

export default function BenchmarksSummary() {
    return (
        <Box className="space-y-6" sx={{ color: "text.primary" }}>
            <Box sx={{ maxWidth: 900 }}>
                <Typography variant="h1" component="h1">
                    Benchmarks
                </Typography>
                <Typography
                    color="text.secondary"
                    sx={{ mt: 1, maxWidth: 780 }}
                >
                    Benchmarks are the validation area for the pipeline. Use
                    them to compare expected examples with actual behavior
                    before relying on a strategy for larger runs.
                </Typography>
            </Box>

            <Box
                sx={{
                    display: "grid",
                    gridTemplateColumns: { xs: "1fr", md: "repeat(3, 1fr)" },
                    gap: 2,
                }}
            >
                {guidance.map((item) => (
                    <Card key={item.title}>
                        <CardContent sx={{ p: 3 }}>
                            <Typography variant="h2" component="h2">
                                {item.title}
                            </Typography>
                            <Typography color="text.secondary" sx={{ mt: 1 }}>
                                {item.text}
                            </Typography>
                        </CardContent>
                    </Card>
                ))}
            </Box>

            <Card>
                <CardContent
                    sx={{
                        p: 3,
                        display: "flex",
                        flexWrap: "wrap",
                        gap: 1.5,
                        alignItems: "center",
                    }}
                >
                    <Typography
                        variant="h2"
                        component="h2"
                        sx={{ mr: { md: "auto" } }}
                    >
                        Choose where to work
                    </Typography>
                    <Button
                        component={Link}
                        href="/benchmarks/workspaces"
                        variant="contained"
                        startIcon={<WorkspacesIcon />}
                        endIcon={<ArrowForwardIcon />}
                    >
                        Workspaces
                    </Button>
                    <Button
                        component={Link}
                        href="/benchmarks/runs"
                        variant="outlined"
                        startIcon={<RunsIcon />}
                        endIcon={<ArrowForwardIcon />}
                    >
                        Runs
                    </Button>
                    <Button
                        component={Link}
                        href="/benchmarks/strategies"
                        variant="outlined"
                        startIcon={<StrategiesIcon />}
                        endIcon={<ArrowForwardIcon />}
                    >
                        Strategies
                    </Button>
                </CardContent>
            </Card>
        </Box>
    );
}
