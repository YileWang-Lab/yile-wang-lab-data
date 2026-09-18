% Data matrix
data = [0.987, -0.156, 0.999; 
        0.988, -0.152, 1; 
        0.777, 0.63, 1; 
        0.982, -0.189, 0.999];

% Variable names
variables = {'Population Density', 'Urban Population', 'Total Workforce', 'Pop. in Urban >1M'};

% Factor names
factors = {'Factor 1', 'Factor 2', 'Communality'};

% Create heatmap
heatmap(factors, variables, data);

% Set title and axis labels
title('Factor Loading Matrix Heatmap');
xlabel('Factors');
ylabel('Variables');
