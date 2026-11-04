"""Listas de nombres y apellidos frecuentes en Colombia/LatAm (minúsculas, sin tildes).

Son listas cortas y a propósito incompletas: la detección de nombres es heurística
y NO sustituye a un modelo de NER. Los nombres que no estén aquí solo se detectan
con contexto (por ejemplo, tras «señor», «nombre:» o «me llamo»).
"""

from __future__ import annotations

import unicodedata
from functools import lru_cache


@lru_cache(maxsize=65536)
def normalize(token: str) -> str:
    """Minúsculas y sin tildes (conserva la ñ como «n» para tolerar escritura sin tilde)."""
    decomposed = unicodedata.normalize("NFD", token.casefold())
    return "".join(c for c in decomposed if not unicodedata.combining(c))


_FIRST_NAMES = """
juan carlos jose luis jorge miguel andres david daniel camilo santiago sebastian felipe
alejandro nicolas mateo samuel diego fernando ricardo eduardo alberto alfonso alvaro arturo
bernardo cesar cristian christian dario edgar edwin efrain emilio enrique ernesto esteban
fabian fabio fabricio felix francisco gabriel german gilberto gonzalo guillermo gustavo
harold hector hernan hugo humberto ivan jaime javier jairo jefferson jeison jhon john
jhonatan jonathan joaquin julian julio leonardo leonel lorenzo manuel marco marcos mario
mauricio maximiliano nestor oscar omar orlando pablo pedro rafael ramiro raul reinaldo rene
roberto rodrigo rogelio roman ruben salvador sergio tomas ulises vicente victor wilmer
wilson william yeison yesid yeferson alexander anderson brayan brian bryan cristobal darwin
deivid dilan dylan elkin elias emmanuel ezequiel fredy freddy gerardo giovanni giovanny
heiner henry hernando ignacio isaac isaias jacobo jesus jhoan joel josue kevin lucas
luciano mauro moises nelson neftali norberto octavio oswaldo patricio rolando saul simon
teodoro tulio uriel walter wilfredo yamid yhon
maria ana laura sofia valentina camila daniela carolina paula andrea natalia juliana
catalina alejandra angela adriana alba alicia amanda amparo angelica antonia beatriz berta
blanca bibiana carmen carmenza cecilia claudia clara constanza consuelo cristina diana dora
elena eliana elisa elizabeth esperanza estefania esther eugenia eva fabiola fanny flor
florencia francia gabriela gladys gloria graciela helena irene isabel isabella ines
jackeline jennifer jessica johana johanna jimena karen karina katherine katerin kelly leidy
leonor lilia liliana lina lorena lucia luz luisa magda manuela marcela margarita mariana
marisol marta martha mayra melissa mercedes mireya monica nancy nelly nidia nora olga
omaira patricia paola pilar rocio rosa rosario ruth sandra sara sharon sheila silvia sonia
stella susana tatiana teresa ximena yadira yamile yaneth yesenia yeimy yolanda yuliana
yurani zulma viviana victoria vanessa veronica wendy yenny yessica ingrid irma judith
julieta kimberly lady lizeth lisbeth maribel maricela marlen marleny martina milena miriam
nathalia nicole noelia paulina rebeca regina ligia lucero luna magdalena maira mabel
marlene dolores soledad paz aurora
angie brenda celeste dayana deisy doris edith emilia estela gisela hilda isabela jazmin
josefina karla lida lilian lucy luzmila maritza nubia piedad rubiela ruby shirley sindy
stephany tania xiomara yaqueline zoraida aida alexandra mariela marcia daisy dayanna
abel adolfo agustin alirio anibal antonio armando augusto aurelio benjamin clemente danilo
duvan eider elmer emerson faber gildardo hamilton harvey hollman horacio ismael jader
leandro libardo marino misael noel olmedo ovidio reinel robinson rodolfo ronald silvio
wilber wilfer yovany jhonny johnny alonso alfredo arnulfo baltazar dairo eduar fredy
"""

_SURNAMES = """
garcia rodriguez martinez lopez gonzalez perez gomez sanchez ramirez torres diaz vargas
castro romero alvarez ruiz mendoza rojas gutierrez ortiz moreno munoz herrera jimenez
medina castillo cardenas ramos aguilar vasquez cruz rios ortega morales reyes silva suarez
guerrero salazar parra pineda quintero zapata velasquez restrepo ospina cardona arango
henao giraldo botero uribe acosta agudelo alarcon aldana alonso arias arevalo avila ayala
baez barrera bautista bedoya benitez bernal bonilla bravo bustamante caballero cabrera
calderon camacho campos cano cardozo carvajal castaneda castellanos cely cespedes chacon
cifuentes contreras correa cortes cuellar delgado duarte duque duran echeverri escobar
espinosa estrada fajardo fernandez flores forero franco fuentes gaitan galeano galindo
gallego gallo garzon gil granados guzman hernandez hurtado ibarra jaramillo lara leon
londono lozano lugo macias maldonado marin marquez marulanda mejia melo mesa millan molina
montoya mora murillo naranjo navarro nieto nino noriega nunez obando ochoa olaya olarte
orozco ordonez osorio pacheco padilla palacios pardo patino pena penaloza pinzon polo
posada prieto puerta quesada quiroga quiroz rangel rey rincon rivas rivera robledo rocha
rueda salamanca salgado salinas sandoval santamaria santos sepulveda serrano solano soto
tamayo tellez toro trujillo valencia valderrama valdes vallejo vega velez venegas vera
villa villamizar villegas zambrano zuluaga zabala orjuela ballesteros cortes
acevedo aguirre alvarado amaya angulo aponte arboleda arenas ariza avendano barbosa barreto
becerra beltran bermudez betancur betancourt bohorquez buitrago burbano caicedo camargo
carrillo ceballos chaparro chaves cuervo daza espitia figueroa florez gamboa gaviria godoy
grajales guevara guerra hoyos ibanez jaimes leal linares losada manrique mantilla mendez
meneses mercado miranda monsalve motta munera murcia ocampo ojeda oliveros otalora otero
pabon paez pinilla plata poveda quevedo quiceno rengifo rendon ricaurte roa rodas roldan
rosero saavedra salcedo sarmiento sierra solorzano tabares tobon tovar urrego usma
valbuena varon velandia vergara vidal villalba villarreal yepes zamora echeverri
"""

# Palabras que además son sustantivos/adjetivos/lugares comunes: no bastan por sí solas
# para declarar un nombre sin contexto.
_AMBIGUOUS = """
rosa luz paz pilar victoria esperanza soledad gloria consuelo amparo mercedes dolores
carmen jesus blanca aurora flor alba clara lady luna marina regina
blanco moreno rey castillo torres mora cruz sol parra prieto pastor guerrero marin salas
vega rios campos bravo santos leon lobo cano vera mesa gil flores franco duque montes
estrada castro serrano delgado valencia ortega santander polo villa rocha puerta nieto
nino lara toro gallo cortes salinas arias correa
sierra plata leal guerra mercado cuervo miranda celeste ruby
"""

FIRST_NAMES: frozenset[str] = frozenset(_FIRST_NAMES.split())
SURNAMES: frozenset[str] = frozenset(_SURNAMES.split())
AMBIGUOUS: frozenset[str] = frozenset(_AMBIGUOUS.split())

# Tratamientos y saludos que anuncian que a continuación viene un nombre.
TITLES: frozenset[str] = frozenset(
    [
        "senor",
        "senora",
        "senores",
        "senoras",
        "sr",
        "sra",
        "don",
        "dona",
        "doctor",
        "doctora",
        "dr",
        "dra",
        "ing",
        "ingeniero",
        "ingeniera",
        "abogado",
        "abogada",
        "licenciado",
        "licenciada",
        "lic",
        "profesor",
        "profesora",
        "prof",
        "estimado",
        "estimada",
        "querido",
        "querida",
        "hola",
        "gracias",
        "saludos",
        "atte",
        "att",
        "atentamente",
        "cordialmente",
    ]
)

# Palabras con mayúscula inicial que NO son nombres (lugares, instituciones, calendario...).
STOPWORDS: frozenset[str] = frozenset(
    [
        "colombia",
        "bogota",
        "medellin",
        "cali",
        "barranquilla",
        "cartagena",
        "bucaramanga",
        "cucuta",
        "pereira",
        "manizales",
        "ibague",
        "pasto",
        "neiva",
        "armenia",
        "popayan",
        "villavicencio",
        "monteria",
        "valledupar",
        "santa",
        "tunja",
        "antioquia",
        "cundinamarca",
        "valle",
        "atlantico",
        "bolivar",
        "santander",
        "boyaca",
        "caldas",
        "risaralda",
        "tolima",
        "huila",
        "narino",
        "meta",
        "cesar",
        "cordoba",
        "sucre",
        "choco",
        "guajira",
        "quindio",
        "caqueta",
        "putumayo",
        "amazonas",
        "mexico",
        "peru",
        "chile",
        "argentina",
        "ecuador",
        "venezuela",
        "brasil",
        "panama",
        "espana",
        "usa",
        "calle",
        "carrera",
        "avenida",
        "diagonal",
        "transversal",
        "autopista",
        "barrio",
        "ciudad",
        "conjunto",
        "edificio",
        "cedula",
        "nit",
        "pasaporte",
        "telefono",
        "celular",
        "correo",
        "direccion",
        "placa",
        "cuenta",
        "banco",
        "bancolombia",
        "davivienda",
        "nequi",
        "daviplata",
        "universidad",
        "hospital",
        "colegio",
        "clinica",
        "ministerio",
        "alcaldia",
        "gobernacion",
        "gobierno",
        "republica",
        "ley",
        "decreto",
        "articulo",
        "resolucion",
        "circular",
        "dian",
        "enero",
        "febrero",
        "marzo",
        "abril",
        "mayo",
        "junio",
        "julio",
        "agosto",
        "septiembre",
        "octubre",
        "noviembre",
        "diciembre",
        "lunes",
        "martes",
        "miercoles",
        "jueves",
        "viernes",
        "sabado",
        "domingo",
        "gracias",
        "cordialmente",
        "atentamente",
        "saludos",
        "buenos",
        "buenas",
        "dias",
        "tardes",
        "noches",
        "presidente",
        "gerente",
        "director",
        "directora",
        "cliente",
        "usuario",
        "titular",
        "paciente",
        "senor",
    ]
)
