from dataclasses import dataclass
from typing import Optional, Dict

# Map each visible sidebar label to a conceptual bylaw group.
BYLAW_GROUP_FOR_LABEL: Dict[str, str] = {
    "Can you Keep Backyard Chickens": "Backyard Chickens",

    "Farm Exemption - Tree Cutting Bylaw": "Forest Conservation",

    "Farm Exemption for Development Charges": "Development Charges",
    "Farm Exemption for Stormwater Charges": "Stormwater",
    "Farm Exemption for SA": "Site Alteration",

    # All LGD-related sidebar entries share the same OFA content and letter.
    "Has Livestock Guardian dog Definition": "Livestock Guardian Dogs",
    "Herding Dog Definition Exists": "Livestock Guardian Dogs",
    "LDG - Definition": "Livestock Guardian Dogs",
}


@dataclass
class BylawContent:
    title: str
    body_md: str
    letter_path: Optional[str]  # relative path to .docx, or None if no template letter


# One BylawContent per conceptual bylaw group.
# The body_md values below are based on the OFA positions from
# "OFA Positions and draft bylaw letters.docx".
BYLAW_CONTENT_FOR_GROUP: Dict[str, BylawContent] = {
    "Development Charges": BylawContent(
        title="OFA position on Development Charge bylaws",
        body_md="""The loss of Ontario farmland

Only about 5% of Ontario’s land base is suitable for agriculture. This finite resource underpins
our ability to produce food, fibre and fuel. As urban development and other non‑agricultural
uses expand, prime farmland is permanently removed from production. Statistics Canada data
show hundreds of thousands of hectares of farmland were lost in just a decade. Ontario cannot
sustain this rate of loss and still maintain a strong domestic food supply.

Development charges as a tool to protect farmland

Development charges are meant to fund growth‑related capital costs. With small adjustments,
they can also help incentivize the protection of agricultural land. In many agricultural
municipalities, farm buildings and structures have historically been exempt from development
charges. When new bylaws or updates are enacted, those exemptions can be dropped
inadvertently unless farmers and councillors are vigilant.

Applying development charges to farm buildings creates a disincentive for farmers to reinvest in
their operations. It undermines farm business viability and can accelerate the loss of farmland.

OFA’s position is that the Development Charges Act should be amended to provide a statutory
exemption for farm buildings and structures. Exempting farm structures while maintaining
charges on other forms of development raises the relative cost of converting farmland to other
uses and creates a financial incentive to keep land in production.

Farm structures and growth‑related capital costs

The purpose of development charges is to pay for increased capital costs required due to
development‑driven service needs. New farm residences (MPAC classifications RU or FRU)
are like other residential units and can reasonably attract development charges because they
contribute to growth‑related infrastructure needs.

However, typical farm buildings (barns, silos, pack sheds, etc.) do not generate the same
growth‑related capital costs. Charging development fees on these structures forces farmers to
pay more than their fair share of municipal capital expenditures.

Standardizing an agricultural exemption for farm buildings through a province‑wide approach
would prevent inequitable treatment of farmers in those municipalities that have not explicitly
provided an exemption. It would directly support the long‑term objective of protecting prime
agricultural areas for ongoing agricultural use and help ensure development charges remain
focused on development that truly generates growth‑related capital costs.""",
        letter_path="letters/development_charges_letter.docx",
    ),

    "Stormwater": BylawContent(
        title="OFA position on Stormwater Fee bylaws",
        body_md="""Municipal stormwater management fees and agriculture

More municipalities are introducing stormwater management fees to pay for the maintenance
and expansion of their water management systems. Because there is no provincial standard
for calculating these fees, each municipality has developed its own approach. Farmers who
have been assessed stormwater fees often face significant and sometimes unpredictable costs.

OFA policy on stormwater fees

OFA believes that stormwater management fees should not be applied to agricultural
properties. Farmland already provides substantial water and environmental benefits to
municipalities, including:

- Absorption and infiltration of stormwater, helping to recharge aquifers, creeks, streams,
  lakes and wetlands.
- Slowing peak flows, which reduces in‑stream erosion and flood risk.
- Filtering contaminants before they reach municipal watercourses.

When these benefits are taken into account, it becomes clear that agricultural lands help to
reduce the burden on municipal stormwater systems rather than increasing it.

Potential for unfair taxation

OFA’s concern is that stormwater management fees can amount to an unfair additional tax on
farms. Municipalities must be able to clearly explain and quantify:

- What specific stormwater service is being provided to an agricultural property, and
- How the fee being charged relates to that service.

Any calculation should explicitly account for the environmental services provided by farmland.

Municipal drains and double charging

Where land is served by municipal drains under the Drainage Act, landowners already pay for
stormwater and drainage services through that system. OFA’s position is that those drains
and the lands served by them should be omitted from additional stormwater management fees.
Charging farmers both through the Drainage Act and a separate stormwater fee constitutes a
form of double payment.

In summary, OFA supports stormwater policies that recognize the environmental benefits of
farmland, avoid double charging and prevent stormwater management fees from becoming an
unjust, additional tax on farm businesses.""",
        letter_path="letters/stormwater_fee_letter.docx",
    ),

    "Site Alteration": BylawContent(
        title="OFA position on Site Alteration bylaws",
        body_md="""Excess soil and agricultural land

Many agricultural producers receive excess soil to improve field conditions and productivity.
When managed properly, the addition of suitable soil can enhance crop production and long‑
term soil health. OFA’s primary concern is to ensure that agricultural land remains productive
and free from contaminants that could threaten food safety, environmental quality or the
long‑term viability of the farm.

Local regulation of site alteration

Farmers receiving excess soil are typically governed by municipal fill or site alteration bylaws.
These bylaws often build on provincial standards for soil quality, testing and oversight.
If provincial requirements are weakened or simplified without care, municipalities may respond
by shifting more of the responsibility and risk onto individual farmers through local bylaws.

OFA’s position is that the generator of the excess soil (the source site) should be responsible
for ensuring that the soil meets all applicable provincial quality requirements before it is spread
on agricultural land. Farmers should not be forced to carry the burden of verifying soil quality
that originates elsewhere.

Protecting productivity and food safety

To protect agricultural productivity and local food safety, OFA advocates for:

- Strong provincial standards governing excess soil quality.
- Clear rules that place responsibility for meeting those standards on the soil generator.
- Municipal bylaws that are consistent with provincial rules and do not place undue
  compliance burdens on the receiving farmer.

Eliminating the risk of contamination to agricultural lands must remain paramount when
developing or updating site alteration bylaws affecting farms.""",
        letter_path=None,  # no template letter available for Site Alteration
    ),

    "Livestock Guardian Dogs": BylawContent(
        title="OFA position on Livestock Guardian Dog bylaws",
        body_md="""Context

Problem predators are an increasing challenge for Ontario livestock farmers. Wildlife attacks
can result in serious financial losses and animal welfare concerns. In recent years, provincial
compensation programs have paid significant amounts to farmers for livestock lost to
predation.

OFA supports the responsible use of Livestock Guardian Dogs (LGDs) as an effective, non‑
lethal tool for protecting livestock from predators. LGDs are particularly important in rural
and remote areas where predator pressure is high and other control methods may be less
effective.

Key principles supported by OFA

1. Support for livestock protection  
   LGDs play a critical role in deterring coyotes, wolves and other predators. Their presence
   helps prevent livestock injury and loss, and can reduce stress in the herd or flock. OFA
   supports the continued use of LGDs as part of humane and effective predator‑management
   strategies.

2. Responsible ownership and training  
   OFA encourages best practices in the selection, training and management of LGDs. Well‑
   managed guardian dogs are bonded to the livestock they protect, supervised appropriately
   and provided with proper veterinary care, housing and nutrition.

3. Public safety and containment  
   Although LGDs may range more widely than typical companion dogs, they must be managed
   in ways that avoid conflicts with neighbours, roadways and public spaces. OFA supports
   clear, workable guidelines on containment and monitoring, especially where agricultural
   land is adjacent to residential or recreational areas.

4. Regulatory clarity and farmer rights  
   OFA supports farmers’ rights to use LGDs as part of legitimate farm operations under
   Ontario’s Farming and Food Production Protection Act (FFPPA). Municipalities should be
   cautious not to apply urban pet ownership standards (for example, strict barking limits,
   collar requirements or dog‑licence rules) in ways that prevent LGDs from performing their
   working role on farms.

5. Coexistence and rural understanding  
   LGDs are part of a broader effort to support coexistence between agriculture and wildlife.
   OFA encourages outreach to rural residents, recreational land users and visitors so they
   understand the role of LGDs and how to behave safely around them.

6. Animal welfare  
   The welfare of LGDs must be protected alongside the livestock they guard. Guardian dogs
   must receive appropriate shelter, nutrition, health care and humane treatment. OFA opposes
   neglect or abandonment of any working animal.

Overall, OFA recognizes LGDs as a valuable, time‑tested tool that can improve animal welfare,
reduce livestock losses and contribute to sustainable predator management when supported by
balanced, farm‑aware municipal bylaws.""",
        letter_path="letters/livestock_guardian_dogs_letter.docx",
    ),

    "Forest Conservation": BylawContent(
        title="OFA position on Forest Conservation / Tree Cutting bylaws",
        body_md="""Tree cover and agriculture

Tree cover is declining in many parts of Ontario, particularly in the south where pressures
from urbanization and land development are greatest. Municipalities are increasingly using
forest conservation or tree cutting bylaws (enabled under Section 135 of the Municipal Act,
2001) to maintain tree cover and regulate the destruction or injuring of trees.

Intersection with farm operations

Many normal agricultural activities involve working in and around treed areas or woodlots.
Without carefully designed exemptions, forest conservation bylaws can inadvertently restrict
a farmer’s ability to:

- Carry out normal farm practices.
- Maintain existing laneways and field access.
- Prevent woodlot encroachment on productive farmland.
- Adjust the farm operation to respond to changing markets.

OFA’s position is that municipalities enacting tree bylaws should explicitly include agricultural
exemptions that allow:

- The destruction or removal of trees as part of normal farm practices.
- The removal of trees that are impeding the passage of agricultural equipment along
  existing laneways within or at the edge of a woodland, or where trees are encroaching on
  productive agricultural land.

Relationship to the Farming and Food Production Protection Act

The Farming and Food Production Protection Act (FFPPA) allows farmers to appeal municipal
bylaws that prohibit or restrict normal farm practices to the Normal Farm Practices Protection
Board. Incorporating clear agricultural exemptions into forest conservation bylaws reduces
the likelihood of conflict with the FFPPA and lowers administrative burdens for both farmers
and municipalities.

In short, OFA supports bylaws that protect tree cover while still allowing farmers to conduct
normal agricultural activities and maintain the productivity of their land.""",
        letter_path="letters/forest_conservation_letter.docx",
    ),

    "Backyard Chickens": BylawContent(
        title="OFA position on Backyard Chicken bylaws",
        body_md="""Context

OFA recognizes the growing interest in keeping backyard chickens in urban and suburban
areas for egg production, education and local food reasons. While these initiatives can help
residents connect with food production, they also raise important questions around animal
welfare, biosecurity, public health and the potential impacts on Ontario’s regulated poultry
sector.

OFA’s support is conditional on backyard chickens being managed under properly crafted and
enforced municipal bylaws that prioritize:

1. Animal welfare  
   Chickens must receive appropriate housing, nutrition, shelter, protection from predators
   and weather, and general good husbandry. OFA encourages municipalities to include
   minimum standards and to provide educational resources or training for prospective backyard
   flock owners. Poorly managed flocks can result in neglect, disease and animal suffering.

2. Biosecurity and disease prevention  
   Backyard flocks can become vectors for avian diseases, including highly pathogenic avian
   influenza (HPAI), which pose serious risks to commercial poultry farms. OFA recommends
   measures such as:
   - Licensing or registration for backyard flocks.
   - Limits on flock size and type.
   - Registration with appropriate provincial programs (for example, the Chicken Farmers of
     Ontario’s Family Food Program).
   - Encouraging regular veterinary oversight and clear deadstock disposal requirements.
   - Ensuring adequate separation from commercial poultry operations.

3. Public health and safety  
   Chickens can carry zoonotic diseases such as salmonella. Municipal bylaws should be
   accompanied by public education on safe handling, hygiene and coop management to protect
   households, visitors and neighbours.

4. Municipal responsibility and local context  
   Municipalities must retain the authority to regulate or, where appropriate, restrict backyard
   chickens based on local density, zoning, enforcement capacity and risk. OFA encourages
   municipalities to craft bylaws in consultation with agricultural and public health experts.

5. Respect for agricultural boundaries  
   OFA emphasizes the need to maintain a clear distinction between small‑scale backyard
   flocks and commercial agriculture. Regulations should ensure that backyard chickens do not
   undermine the economic viability, biosecurity or regulatory integrity of Ontario’s poultry
   sector.

6. Education and outreach  
   OFA supports educational initiatives that promote responsible animal care and help the
   public understand both the opportunities and the risks associated with backyard chickens.

In summary, OFA conditionally supports the keeping of backyard chickens where municipal
bylaws are robust, enforceable and designed to protect animal welfare, public health and the
broader interests of Ontario’s agricultural industry.""",
        letter_path="letters/backyard_chickens_letter.docx",
    ),
}


def get_content_for_label(label: str) -> Optional[BylawContent]:
    """Return the BylawContent for a given sidebar label, or None if unmapped."""
    group = BYLAW_GROUP_FOR_LABEL.get(label)
    if group is None:
        return None
    return BYLAW_CONTENT_FOR_GROUP.get(group)
