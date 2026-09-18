import matplotlib.pyplot as plt

from wordcloud import WordCloud
# Directly paste your text here between the triple quotes
text = """
Computers, communications, and other services (as a percentage of commercial service exports)
Report the commodity exports of the economy, remaining (as a percentage of the total commodity exports)
Commodity exports to developing economies in Latin America and the Caribbean (as a percentage of total commodity exports)
Exports of goods to high-income economies (as a percentage of total commodity exports)
Manufacturing exports (as a percentage of commodity exports)
Food exports (as a percentage of commodity exports)
Import value of commercial services (current price in US dollars)
Report on commodity imports of the economy (current price in US dollars)
Commodity imports from developing economies in the Middle East and North Africa region (as a percentage of total commodity imports)
Import of goods from developing economies outside the region (as a percentage of total goods imports)
Imports of ores and metals (percentage of commodity imports)
Fuel imports (as a percentage of commodity imports)
Most Favored Nation Weighted Average Tax Rate for Primary Products (%)
Simple average applicable tax rate for primary products (%)
Most Favored Nation Weighted Average Tax Rate for All Products (%)
Simple average applicable tax rate for all products (%)
Most Favored Nation Weighted Average Tax Rate for Industrial Products (%)
Simple average applicable tax rate for industrial products (%)
Import volume index (2000=100)
International tourism, travel project expenses (current price in US dollars)
International tourism, revenue (as a percentage of total exports)
Unmet contraceptive needs (proportion of married women aged 15-49)
Rural population (percentage of total population)
Birth registration completeness (percentage)
Total population, female
Population growth (annual percentage)
Gender ratio of birth population (females per 1000 males)
Population ages 75-79, female (% of female population)
Total population aged 65 and above
The total number of people aged 65 and above, female
Population ages 60-64, female (% of female population)
Population ages 50-54, female (% of female population)
Population ages 40-44, female (% of female population)
Population ages 30-34, female (% of female population)
Population ages 20-24, female (% of female population)
Total population aged 15-64, male
Population ages 15-19, female (% of female population)
Population ages 5-9, female (% of female population)
Population ages 0-4, female (% of female population)
Household headed by women (proportion of households headed by women)
Total fertility rate (per capita female fertility)
Infant mortality rate, male (per 1000 live births)
Contraceptive validity, modern methods (% of women ages 15-49)
Mortality rate, adults, females (per thousand adult females)
Edible iodized salt (proportion of households)
International migrants, total
Children in employment, wage workers (% of children in employment, ages 7-14)
Unemployment, total (% of total labor force) (national estimate)
Unemployment, female (% of female labor force) (national estimate)
Unemployment with intermediate education (% of total labor force with intermediate education)
Unemployment with basic education, male (% of male labor force with basic education)
Unemployment with advanced education, female (% of female labor force with advanced education)
Unemployment, young male (% of male labor force ages 15-24) (national estimate)
Labor force, female (percentage of total labor force)
Labor force with intermediate education (% of total working age population with intermediate education)
Labor force participation rate, total (% of total population ages 15+) (national estimate)
Ratio of female to male labor force participation rate (%) (national estimate)
Labor force with basic education, male (% of male working age population with basic education)
Labor force with advanced education, female (% of female working age population with advanced education)
Labor force participation rate of population aged 15-24, total (%) (estimated by simulated labor organizations)
Labor force participation rate, female (percentage of female population aged 15-24) (estimated by simulated labor organizations)
Average working hours of children, working only, ages 7-14 (hours per week)
Average working hours of children, working only, female, ages 7-14 (hours per week)
Average working hours of children, study and work, male, ages 7-14 (hours per week)
Girls engaged in economic activities (proportion of girls aged 7-14)
Employment rate of child labor in the service industry (proportion of economically active children aged 7-14)
Children in employment, self-employed, male (% of male children in employment, ages 7-14)
Employment rate of female child workers in the manufacturing industry (percentage of girls aged 7-14 participating in economic activities)
Per capita GDP of employed population (2011 constant purchasing power parity US dollars)
Children in employment, unpaid family workers (% of children in employment, ages 7-14)
Wage and salaried workers, male (% of male employment)
Employment rate of female vulnerable groups (proportion of all female employees)
Employment to population ratio, 15+, male (%) (national estimate)
Self employed, total (% of total employment)
Employers, male (% of male employment)
Ratio of male employed population aged 15-24 (percentage) (estimated by simulated labor organizations)
Agricultural employed personnel (percentage of total employment)
Employment rate of agricultural male and child laborers (percentage of boys aged 7-14 participating in economic activities)
Annualized average growth rate in per capital real survey mean consumption or income, bottom 40% of population (%)
Minimum 20% share of income
Revenue share of up to 20%
Success rate of pulmonary tuberculosis treatment (proportion of registered cases)
The incidence of emaciation (percentage of children under 5 years old)
Mortality caused by road traffic injury (per 100000 people)
The incidence of malnutrition, age and height (percentage of children under 5 years old)
Overweight rate, male (percentage of children under 5 years old)
People practicing open defense (% of population)
Maternal mortality rate (model estimate, proportion per 100000 live births)
Diabetes validity (% of population ages 20 to 79)
Pregnant women receiving prenatal care (percentage)
Specialist surgical work force (per 100000 population)
Female smoking rate (proportion of smoking women to all adults)
Lifetime risk of maternal mortality (rates vary by country)
Incident of malaria (per 1000 population at risk)
Community health service personnel (per 1000 people)
Immunization, HepB3 (% of one year old children)
Adults (ages 15+) newly affected with HIV
Children infected with AIDS virus (0 to 14 years old)
Neonatal mortality rate (per thousand live births)
Mortality rate, under 5 years old, male (per thousand people)
Adult women infected with HIV (percentage of HIV infected individuals aged 15 and above)
Cause of death, by entry (% of total)
Condom usage rate, population aged 15-24, female (percentage of female population aged 15-24)
Human Capital Index, Lower Bound (Value Range 0-1)
Expenditure (as a percentage of GDP)
Interest payment (percentage of expenses)
Goods and services expenditure (current price in local currency)
Income tax, profit tax, and capital gains tax (as a percentage of total tax revenue)
Other taxes (percentage of fiscal revenue)
Tariffs and other import taxes (as a percentage of tax revenue)
Goods and Services Tax (Present Value in Local Currency)
Income, excluding donations (in current domestic currency units)
Grants and other income (in current local currency units)
Net investment in non-financial assets (current LCU)
Central government debt, total amount (current local currency units)
Debt to the central government, as a percentage of GDP
Loan interest rate (percentage)
Consumer Price Index (2010=100)
Generalized currency (current local currency unit)
Net domestic credit (current price in local currency units)
The months in which the total reserve can pay for imports
Domestic credit to private sector by banks (% of GDP)
The ratio of bank capital to assets (percentage)
Marine protected areas (percentage of territorial waters)
Annual freshwater extraction volume, total amount (percentage of internal resources)
Annual fresh water extraction, domestic water (percentage of total fresh water extraction)
Capture fisheries production (metric tons)
Population in urban agglomerations with a population exceeding 1 million (as a percentage of the total population)
Population living in sludge (% of urban population)
Population density (number of people per kilometer of land area)
Carbon dioxide emissions from the transportation sector (as a percentage of total fuel combustion)
Carbon dioxide emissions from residential buildings, commercial and public services (as a percentage of total fuel combustion)
Threatened birds
Nitrous oxide emissions (% change from 1990)
Agricultural nitrous oxide emissions (percentage of total)
Energy related methane emissions (percentage of total)
HFC gas emissions (thousands of metric tons of carbon dioxide equivalent)
Other greenhouse gas emissions, HFC, PFC, and SF6 (thousands of metric tons of carbon dioxide equivalent)
Carbon dioxide emissions (kg/PPP USD GDP)
Carbon dioxide emissions (thousands of tons)
Carbon dioxide intensity (kg/petroleum equivalent energy use kg)
Energy usage per $1000 GDP (constant PPP in 20011) in kilograms of petroleum equivalent
Economic and industrial per capita GDP (in 2015 constant US dollars)
Total investment in electricity production and supply industry (10000 yuan)
High tech exports (current price in US dollars)
Energy consumption and structural energy consumption elasticity coefficient (-)
Elastic coefficient of electricity consumption (-)
Total energy consumption (10000 tons of standard coal)
The proportion of coal to total energy consumption (%)
Generalized currency (current local currency unit)
Net domestic credit (current price in local currency units)
The months in which the total reserve can pay for imports
Domestic credit to private sector by banks (% of GDP)
The ratio of bank capital to assets (percentage)
Marine protected areas (percentage of territorial waters)
Annual freshwater extraction volume, total amount (percentage of internal resources)
Annual fresh water extraction, domestic water (percentage of total fresh water extraction)
Capture fisheries production (metric tons)
Population in urban agglomerations with a population exceeding 1 million (as a percentage of the total population)
Population living in sludge (% of urban population)
Population density (number of people per kilometer of land area)
Carbon dioxide emissions from the transportation sector (as a percentage of total fuel combustion)
Carbon dioxide emissions from residential buildings, commercial and public services (as a percentage of total fuel combustion)
Threatened birds
Nitrous oxide emissions (% change from 1990)
Agricultural nitrous oxide emissions (percentage of total)
Energy related methane emissions (percentage of total)
HFC gas emissions (thousands of metric tons of carbon dioxide equivalent)
Other greenhouse gas emissions, HFC, PFC, and SF6 (thousands of metric tons of carbon dioxide equivalent)
Carbon dioxide emissions (kg/PPP USD GDP)
Carbon dioxide emissions (thousands of tons)
Carbon dioxide intensity (kg/petroleum equivalent energy use kg)
Energy usage per $1000 GDP (constant PPP in 20011) in kilograms of petroleum equivalent
Economic and industrial per capita GDP (in 2015 constant US dollars)
Total investment in electricity production and supply industry (10000 yuan)
High tech exports (current price in US dollars)
Energy consumption and structural energy consumption elasticity coefficient (-)
Elastic coefficient of electricity consumption (-)
Total energy consumption (10000 tons of standard coal)

The proportion of oil to total energy consumption (%)
The proportion of natural gas to total energy consumption (%)
The proportion of primary electricity and other energy sources to the total energy consumption (%)
Population and social population density (number of people per kilometer of land area)
Urban population (proportion to total population)
Labor force, total number
The population in urban agglomerations with a population exceeding one million.
Environment and emissions of methane emissions (thousands of tons of carbon dioxide equivalent)
Carbon dioxide emissions (thousands of tons)
Farmland (percentage of land area)
Economic and industrial per capita GDP (in 2015 constant US dollars)
Total investment in electricity production and supply industry (10000 yuan)
High tech exports (current price in US dollars)
Energy consumption and structural energy consumption elasticity coefficient (-)
Elastic coefficient of electricity consumption (-)
Total energy consumption (10000 tons of standard coal)
The proportion of coal to total energy consumption (%)
The proportion of oil to total energy consumption (%)
The proportion of natural gas to total energy consumption (%)
The proportion of primary electricity and other energy sources to the total energy consumption (%)
Population and social population density (number of people per kilometer of land area)
Urban population (proportion to total population)
Labor force, total number
The population in urban agglomerations with a population exceeding one million.
Environment and emissions of methane emissions (thousands of tons of carbon dioxide equivalent)
Carbon dioxide emissions (thousands of tons)
Farmland (percentage of land area)
Economic and industrial per capita GDP (in 2015 constant US dollars)
Total investment in electricity production and supply industry (10000 yuan)
High tech exports (current price in US dollars)
Energy consumption and structural energy consumption elasticity coefficient (-)
Elastic coefficient of electricity consumption (-)
Total energy consumption (10000 tons of standard coal)
The proportion of coal to total energy consumption (%)
The proportion of oil to total energy consumption (%)
The proportion of natural gas to total energy consumption (%)
The proportion of primary electricity and other energy sources to the total energy consumption (%)
Population and social population density (number of people per kilometer of land area)
Urban population (proportion to total population)
Labor force, total number
The population in urban agglomerations with a population exceeding one million.
Environment and emissions of methane emissions (thousands of tons of carbon dioxide equivalent)
Carbon dioxide emissions (thousands of tons)
Farmland (percentage of land area)
Economic and industrial per capita GDP (in 2015 constant US dollars)
Total investment in electricity production and supply industry (10000 yuan)
High tech exports (current price in US dollars)
Energy consumption and structural energy consumption elasticity coefficient (-)
Elastic coefficient of electricity consumption (-)
Total energy consumption (10000 tons of standard coal)
The proportion of coal to total energy consumption (%)
The proportion of oil to total energy consumption (%)
The proportion of natural gas to total energy consumption (%)
The proportion of primary electricity and other energy sources to the total energy consumption (%)
Population and social population density (number of people per kilometer of land area)
Urban population (proportion to total population)
Labor force, total number
The population in urban agglomerations with a population exceeding one million.
Environment and emissions of methane emissions (thousands of tons of carbon dioxide equivalent)
Carbon dioxide emissions (thousands of tons)
Farmland (percentage of land area)
High tech exports (current price in US dollars)
Energy consumption and structural energy consumption elasticity coefficient (-)
Elastic coefficient of electricity consumption (-)
Total energy consumption (10000 tons of standard coal)
The proportion of coal to total energy consumption (%)
The proportion of oil to total energy consumption (%)
The proportion of natural gas to total energy consumption (%)
The proportion of primary electricity and other energy sources to the total energy consumption (%)
Population and social population density (number of people per kilometer of land area)
Urban population (proportion to total population)
Labor force, total number
The population in urban agglomerations with a population exceeding one million.
Environment and emissions of methane emissions (thousands of tons of carbon dioxide equivalent)
Carbon dioxide emissions (thousands of tons)
Farmland (percentage of land area)

High tech exports (current price in US dollars)
Energy consumption and structural energy consumption elasticity coefficient (-)
Elastic coefficient of electricity consumption (-)
Total energy consumption (10000 tons of standard coal)
The proportion of coal to total energy consumption (%)
The proportion of oil to total energy consumption (%)
The proportion of natural gas to total energy consumption (%)
The proportion of primary electricity and other energy sources to the total energy consumption (%)
Population and social population density (number of people per kilometer of land area)
Urban population (proportion to total population)
Labor force, total number
The population in urban agglomerations with a population exceeding one million.
Environment and emissions of methane emissions (thousands of tons of carbon dioxide equivalent)
Carbon dioxide emissions (thousands of tons)
Farmland (percentage of land area)

High tech exports (current price in US dollars)
Energy consumption and structural energy consumption elasticity coefficient (-)
Elastic coefficient of electricity consumption (-)
Total energy consumption (10000 tons of standard coal)
The proportion of coal to total energy consumption (%)
The proportion of oil to total energy consumption (%)
The proportion of natural gas to total energy consumption (%)
The proportion of primary electricity and other energy sources to the total energy consumption (%)
Population and social population density (number of people per kilometer of land area)
Urban population (proportion to total population)
Labor force, total number
The population in urban agglomerations with a population exceeding one million.
Environment and emissions of methane emissions (thousands of tons of carbon dioxide equivalent)
Carbon dioxide emissions (thousands of tons)
Farmland (percentage of land area)
Economics and Industry
Energy consumption and structure
Population and Social Category
Environment and emissions
Economics and Industry
Energy consumption and structure
Population and Social Category
Environment and emissions
Economics and Industry
Energy consumption and structure
Population and Social Category
Environment and emissions
Economics and Industry
Energy consumption and structure
Population and Social Category
Environment and emissions
Per capita GDP (in 2015 constant US dollars)
Total investment in electricity production and supply industry (10000 yuan)
High tech exports (current price in US dollars)
Energy consumption elasticity coefficient (-)
Per capita GDP (in 2015 constant US dollars)
Total investment in electricity production and supply industry (10000 yuan)
High tech exports (current price in US dollars)
Energy consumption elasticity coefficient (-)
Per capita GDP (in 2015 constant US dollars)
Total investment in electricity production and supply industry (10000 yuan)
High tech exports (current price in US dollars)
Energy consumption elasticity coefficient (-)
"""

# Use jieba to segment the text
#分词
#words = jieba.lcut(text)
#words_str = ' '.join(words)
# 自定义字体转换函数，将所有字体倾斜15度

# Create and configure the WordCloud object
wordcloud = WordCloud(
    font_path='C:/Windows/Fonts/msyh.ttc',  # This is an example path to a font supporting Chinese characters
    background_color='white',
    width=800,
    height=600,
    max_words=300,
    prefer_horizontal=1.1,
    min_font_size=10,
    max_font_size=100,
    collocations=True,
    font_step = 0.5 ,

# 控制字体大小的步长
).generate(text)

# Display the generated WordCloud
plt.figure(figsize=(10, 8))
plt.imshow(wordcloud, interpolation='bilinear')
plt.axis('off')  # Hide the axes
plt.show()

# Save the WordCloud image to a file
wordcloud.to_file('wordcloud.png')