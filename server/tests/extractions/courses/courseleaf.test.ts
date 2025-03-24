import { describe, test } from "vitest";
import { assertExtraction, EXTRACTION_TIMEOUT } from "../..";

// https://catalog.upenn.edu/courses/

describe("Courseleaf", { timeout: EXTRACTION_TIMEOUT }, () => {
  describe("University of Pennsylvania", () => {
    test("List of course details", async () => {
      await assertExtraction("https://catalog.upenn.edu/courses/alan/", [
        {
          course_id: "ALAN 0300",
          course_name: "Intermediate Mongolian I",
          course_description: `Mongolian is the national language of the independent State of Mongolia and the language of the nomadic warriors Genghis Khan (known to the Mongolians themselves as Chinggis Khan). It is also spoken in China and Siberia. Today Mongolian musical styles like throat singing (khoomii), products like cashmere (nooluur), and tourism to visit Mongolia's nomadic herders (malchid) are making a mark on the world stage. In this class the students will continue with the basics of modern Mongolian language, as spoken in Ulaanbaatar "Red Hero," the country's capital. They will learn in the phonetic Cyrillic script, which was adapted to Mongolian language from Russian in 1945, with a few additional letters. Intermediate and more advanced grammar will be taught through communicative methodology. Students will also have opportunity to experience Mongolian arts, culture, and cooking in and out of class. This is the first semester of Intermediate Mongolian. By the end of two semesters intermediate Mongolian, students will have learned all the noun forms, and all the major verb forms and will be able to form complex, multi-clause sentences, telling stories, expressing their feelings, and making arguments and explanations. They should be able to interact in all basic "survival" situations in Mongolia.`,
          course_prerequisites: "ALAN 0200",
          course_credits_min: 1,
          course_credits_max: 1,
          course_credits_type: undefined,
        },
        {
          course_id: "ALAN 0400",
          course_name: "Intermediate Mongolian II",
          course_description: `This course is a continuation of Intermediate Mongolian I. Mongolian is the national language of the independent State of Mongolia and the language of the nomadic warriors Genghis Khan (known to the Mongolians themselves as Chinggis Khan). It is also spoken in China and Siberia. Today Mongolian musical styles like throat singing (khoomii), products like cashmere (nooluur), and tourism to visit Mongolia's nomadic herders (malchid) are making a mark on the world stage. In this class the students will continue with the basics of modern Mongolian language, as spoken in Ulaanbaatar "Red Hero," the country's capital. They will learn in the phonetic Cyrillic script, which was adapted to Mongolian language from Russian in 1945, with a few additional letters. Intermediate and more advanced grammar will be taught through communicative methodology. Students will also have opportunity to experience Mongolian arts, culture, and cooking in and out of class. This is the first semester of Intermediate Mongolian. By the end of two semesters intermediate Mongolian, students will have learned all the noun forms, and all the major verb forms and will be able to form complex, multi-clause sentences, telling stories, expressing their feelings, and making arguments and explanations. They should be able to interact in all basic "survival" situations in Mongolia.`,
          course_prerequisites: "ALAN 0300",
          course_credits_min: 1,
          course_credits_max: 1,
          course_credits_type: undefined,
        },
        {
          course_id: "ALAN 5100",
          course_name: "Elementary Mongolian I",
          course_description:
            "Mongolian is the national language of the independent State of Mongolia and the",
          course_prerequisites: undefined,
          course_credits_min: 1,
          course_credits_max: 1,
          course_credits_type: undefined,
        },
        {
          course_id: "ALAN 5200",
          course_name: "Elementary Mongolian II",
          course_description: `This class is a continuation of Elementary Mongolian I and will build on the lessons learned in that class. Mongolian is the national language of the independent State of Mongolia and the language of the nomadic warriors Genghis Khan (known to the Mongolians themselves as Chinggis Khan). It is also spoken in China and Siberia. Students will learn the basics of modern Mongolian language, as spoken in Ulaanbaatar "Red Hero," the country's capital. They will learn in the phonetic Cyrillic script, which was adapted to Mongolian language from Russian in 1945, with a few additional letters. Basic grammar will be taught through communicative methodology. Students will also have opportunity to experience Mongolian arts, culture, and cooking in and out of class.`,
          course_prerequisites: undefined,
          course_credits_min: 1,
          course_credits_max: 1,
          course_credits_type: undefined,
        },
        {
          course_id: "ALAN 5300",
          course_name: "Intermediate Mongolian I",
          course_description: `Mongolian is the national language of the independent State of Mongolia and the language of the nomadic warriors Genghis Khan (known to the Mongolians themselves as Chinggis Khan). It is also spoken in China and Siberia. Today Mongolian musical styles like throat singing (khoomii), products like cashmere (nooluur), and tourism to visit Mongolia's nomadic herders (malchid) are making a mark on the world stage. In this class the students will continue with the basics of modern Mongolian language, as spoken in Ulaanbaatar "Red Hero," the country's capital. They will learn in the phonetic Cyrillic script, which was adapted to Mongolian language from Russian in 1945, with a few additional letters. Intermediate and more advanced grammar will be taught through communicative methodology. Students will also have opportunity to experience Mongolian arts, culture, and cooking in and out of class. This is the first semester of Intermediate Mongolian. By the end of two semesters intermediate Mongolian, students will have learned all the noun forms, and all the major verb forms and will be able to form complex, multi-clause sentences, telling stories, expressing their feelings, and making arguments and explanations. They should be able to interact in all basic "survival" situations in Mongolia.`,
          course_prerequisites: "ALAN 5200",
          course_credits_min: 1,
          course_credits_max: 1,
          course_credits_type: undefined,
        },
        {
          course_id: "ALAN 5400",
          course_name: "Intermediate Mongolian II",
          course_description: `his course is a continuation of Intermediate Mongolian I. Mongolian is the national language of the independent State of Mongolia and the language of the nomadic warriors Genghis Khan (known to the Mongolians themselves as Chinggis Khan). It is also spoken in China and Siberia. Today Mongolian musical styles like throat singing (khoomii), products like cashmere (nooluur), and tourism to visit Mongolia's nomadic herders (malchid) are making a mark on the world stage. In this class the students will continue with the basics of modern Mongolian language, as spoken in Ulaanbaatar "Red Hero," the country's capital. They will learn in the phonetic Cyrillic script, which was adapted to Mongolian language from Russian in 1945, with a few additional letters. Intermediate and more advanced grammar will be taught through communicative methodology. Students will also have opportunity to experience Mongolian arts, culture, and cooking in and out of class. This is the first semester of Intermediate Mongolian. By the end of two semesters intermediate Mongolian, students will have learned all the noun forms, and all the major verb forms and will be able to form complex, multi-clause sentences, telling stories, expressing their feelings, and making arguments and explanations. They should be able to interact in all basic "survival" situations in Mongolia.`,
          course_prerequisites: "ALAN 5300",
          course_credits_min: 1,
          course_credits_max: 1,
          course_credits_type: undefined,
        },
      ]);
    });
  });

  describe("Texas A&M International University", () => {
    test("List of course details", async () => {
      await assertExtraction(
        "https://catalog.tamiu.edu/course-descriptions/port/",
        [
          {
            course_id: "PORT 1311",
            course_name: "Beginning Portuguese I",
            course_description:
              "In this course, students will acquire fundamental skills in listening comprehension, speaking, reading, and writing. Includes basic vocabulary, grammatical structures and culture.",
            course_credits_min: undefined,
            course_credits_max: undefined,
            course_credits_type: undefined,
          },
          {
            course_id: "PORT 1312",
            course_name: "Beginning Portuguese II",
            course_description:
              "A continuation of PORT 1311, students will acquire additional skills in listening comprehension, speaking, reading, and writing. Includes basic vocabulary, grammatical structures, and culture.",
            course_prerequisites: "PORT 1311 or consent of instructor",
            course_credits_min: undefined,
            course_credits_max: undefined,
            course_credits_type: undefined,
          },
          {
            course_id: "PORT 1620",
            course_name: "Beginning Portuguese I and II",
            course_description:
              "An intensive oral and written introduction to Portuguese; student will acquire fundamental skills in listening comprehension, speaking, reading and writing. Includes basic vocabulary, grammatical structures, and culture. This course offers the student a one-semester course equivalent to PORT 1311 and PORT 1312.",
            course_credits_min: undefined,
            course_credits_max: undefined,
            course_credits_type: undefined,
          },
          {
            course_id: "PORT 3301",
            course_name: "Intensive Portuguese",
            course_description:
              "Conducted in Portuguese. This course is designed for Spanish speakers or for highly-motivated students with experience in another Romance language. Special emphasis on making the transition from Spanish to Portuguese using a communicative approach with emphasis on all language skills. This course may be used to meet the University foreign language Core Curriculum requirements or the second Romance language degree requirement in Spanish.",
            course_prerequisites:
              "Twelve hours of Spanish or another Romance Language or consent of the instructor",
            course_credits_min: undefined,
            course_credits_max: undefined,
            course_credits_type: undefined,
          },
          {
            course_id: "PORT 3324",
            course_name: "Luso-Brazilian Lit&Culture",
            course_description:
              "Conducted in Portuguese. Thematic examination of some of the major cultural developments, overview of literary periods, and introduction to the major literary figures of Portugal, Brazil, and the Luso-African countries.",
            course_prerequisites: "PORT 3301",
            course_credits_min: undefined,
            course_credits_max: undefined,
            course_credits_type: undefined,
          },
        ]
      );
    });

    test("List of course details, some have multiple prerequisites", async () => {
      await assertExtraction(
        "https://catalog.tamiu.edu/course-descriptions/phys/",
        [
          {
            course_id: "PHYS 1101",
            course_name: "General Physics I Lab",
            course_description:
              "Laboratory‐based course to accompany PHYS 1301. Laboratory experiments reinforce PHYS 1301 principle of physics, and place importance on scientific communication and collaboration, as well as measurement methods, data collection, basic error analysis, and preparation of laboratory report.Carries no credit towards a major or minor in physics.",
            course_prerequisites: undefined,
            course_credits_min: undefined,
            course_credits_max: undefined,
            course_credits_type: undefined,
          },
          {
            course_id: "PHYS 1102",
            course_name: "General Physics II Lab",
            course_description:
              "Laboratory‐based course to accompany PHYS 1302. Laboratory experiments reinforce PHYS 1302 principle of physics, and place importance on scientific communication & collaboration, as well as measurement methods, data collection, basic error analysis, and preparation of laboratory report. Carries no credit toward a major or minor in physics.",
            course_prerequisites: "PHYS 1301 and PHYS 1101",
            course_credits_min: undefined,
            course_credits_max: undefined,
            course_credits_type: undefined,
          },
          {
            course_id: "PHYS 1170",
            course_name: "Survey of Physical Science Lab",
            course_description:
              "Laboratory course to accompany PHYS 1370. Laboratory exercises reinforce PHYS 1370 lecture material and place importance on scientific communication and collaboration as well as measurement methods. Some mention is made of uncertainty and basic error analysis.",
            course_prerequisites: undefined,
            course_credits_min: undefined,
            course_credits_max: undefined,
            course_credits_type: undefined,
          },
          {
            course_id: "PHYS 1301",
            course_name: "General Physics I",
            course_description:
              "Fundamental principles of physics, is the first of a two semester sequence in General Physics, using algebra and trigonometry; the principles and applications of classical mechanics and thermodynamics. Topics include: kinematics, dynamics, gravitation, energy, momentum, simple harmonic motion, fluid and heat; with emphasis on problem solving. Carries no credit toward a major or minor in physics.",
            course_prerequisites: "MATH 1316 or MATH 2412",
            course_credits_min: undefined,
            course_credits_max: undefined,
            course_credits_type: undefined,
          },
          {
            course_id: "PHYS 1302",
            course_name: "General Physics II",
            course_description:
              "Fundamental principles of physics, is the continuation of PHYS 1301, using algebra and trigonometry; the principles and applications of electricity and magnetism. Topics include: electrostatics, circuits, electromagnetism, waves, optics, and modern physics; with emphasis on problem solving. Carries no credit toward a major or minor in physics.",
            course_prerequisites: "PHYS 1301 and PHYS 1101",
            course_credits_min: undefined,
            course_credits_max: undefined,
            course_credits_type: undefined,
          },
          {
            course_id: "PHYS 1370",
            course_name: "Survey of Physical Science",
            course_description:
              "An introductory survey of physical science. Topics include physics (motion, forces, waves and thermodynamics), chemistry (periodic table, reactions), earth science (geology, weather, biosphere and environment) and astronomy (astronomical history, planetary astronomy, stellar astronomy and cosmology). Designed to fulfill laboratory science core curriculum requirements.",
            course_prerequisites: undefined,
            course_credits_min: undefined,
            course_credits_max: undefined,
            course_credits_type: undefined,
          },
          {
            course_id: "PHYS 2125",
            course_name: "University Physics I Lab",
            course_description:
              "Laboratory course to accompany PHYS 2325. Laboratory experiments reinforce theoretical principles from PHYS 2325 and place importance on scientific communication and collaboration, as well as measurement methods, data collection, uncertainty and error analysis, and preparation of laboratory reports.",
            course_prerequisites: undefined,
            course_credits_min: undefined,
            course_credits_max: undefined,
            course_credits_type: undefined,
          },
          {
            course_id: "PHYS 2126",
            course_name: "University Physics II Lab",
            course_description:
              "Laboratory course to accompany PHYS 2326. Laboratory experiments reinforce theoretical principles from PHYS 2326 and place importance on scientific communication and collaboration, as well as measurement methods, data collection, uncertainty and error analysis, and preparation of laboratory reports.",
            course_prerequisites: undefined,
            course_credits_min: undefined,
            course_credits_max: undefined,
            course_credits_type: undefined,
          },
          {
            course_id: "PHYS 2325",
            course_name: "University Physics I",
            course_description:
              "A calculus‐based treatment of the fundamental principles and applications of classical mechanics and thermodynamics for science and engineering majors. This course is the first of a two‐semester sequence in University Physics. Topics include one‐, two‐, and three‐dimensional motion, forces and Newton's laws, momentum conservation, energy conservation, gravitation, rotational dynamics, angular momentum, fluid mechanics, waves, simple harmonic motion, and thermodynamics.",
            course_prerequisites: "MATH 2413 or equivalent",
            course_credits_min: undefined,
            course_credits_max: undefined,
            course_credits_type: undefined,
          },
          {
            course_id: "PHYS 2326",
            course_name: "University Physics II",
            course_description:
              "A calculus‐based treatment of the fundamental principles and applications of electricity and magnetism for science and engineering majors. This course is a continuation of PHYS 2325. Topics include electrostatics, circuits, electromagnetism, electromagnetic waves, optics, and modern physics.",
            course_prerequisites:
              "MATH 2414 or equivalent (or concurrent enrollment therein) and PHYS 2325 and PHYS 2125",
            course_credits_min: undefined,
            course_credits_max: undefined,
            course_credits_type: undefined,
          },
          {
            course_id: "PHYS 3305",
            course_name: "Optics and Wave Theory",
            course_description:
              "A detailed study of optics. Topics include thin and thick lenses, the lensmaker's equation, apertures, optical machines, interference, Fresnel and Fraunhofer diffraction and polarization, the Cornu Spiral. Electromagnetic waves, geometric optics, physical optics, optical instruments, lasers and holography.",
            course_prerequisites: "PHYS 2326/PHYS 2126, MATH 2415",
            course_credits_min: undefined,
            course_credits_max: undefined,
            course_credits_type: undefined,
          },
          {
            course_id: "PHYS 3310",
            course_name: "Modern Physics",
            course_description:
              "An introduction to the foundations of modern physics. Topics include special and general relativity, kinetic theory of matter, electromagnetic quantization, light and energy, wave-matter duality of light, the Schredinger Equation, nuclear physics and elementary particle theory.",
            course_prerequisites: "PHYS 2326/PHYS 2126",
            course_credits_min: undefined,
            course_credits_max: undefined,
            course_credits_type: undefined,
          },
          {
            course_id: "PHYS 3315",
            course_name: "Classical Mechanics",
            course_description:
              "Topics include kinematics of particles and particle systems in one to three dimensions, rigid body rotation, gravitation, Lagrangian and Hamiltonian dynamics, periodic motion, and small oscillations.",
            course_prerequisites: "PHYS 2326/PHYS 2126 and MATH 3330",
            course_credits_min: undefined,
            course_credits_max: undefined,
            course_credits_type: undefined,
          },
          {
            course_id: "PHYS 3320",
            course_name: "Electromagnetic Field Theory",
            course_description:
              "A mathematical treatment of the fundamentals of classical electromagnetic theory. Topics include electrodynamics, vector calculus, theory of dielectrics, magnetostatic fields, electromagnetic induction, magnetic fields of currents, and Maxwell's equations.",
            course_prerequisites: "PHYS 2326/2126 and MATH 3330",
            course_credits_min: undefined,
            course_credits_max: undefined,
            course_credits_type: undefined,
          },
          {
            course_id: "PHYS 3325",
            course_name: "Thermodynamics",
            course_description:
              "A mathematical treatment of the fundamentals of thermal physics. Topics include the concepts of temperature, equation of state, first and second laws of thermodynamics, entropy, change of phase, and thermodynamic functions.",
            course_prerequisites: "PHYS 2326/2126 and MATH 2415",
            course_credits_min: undefined,
            course_credits_max: undefined,
            course_credits_type: undefined,
          },
          {
            course_id: "PHYS 4199",
            course_name: "Special Topics in Physics",
            course_description:
              "Selected topics in physics are covered, depending on student interest. Credit will be given more than once if the topic varies.",
            course_prerequisites: "Permission of instructor",
            course_credits_min: undefined,
            course_credits_max: undefined,
            course_credits_type: undefined,
          },
          {
            course_id: "PHYS 4299",
            course_name: "Special Topics in Physics",
            course_description:
              "Selected topics in physics are covered, depending on student interest. Credit will be given more than once if the topic varies.",
            course_prerequisites: "Permission of instructor",
            course_credits_min: undefined,
            course_credits_max: undefined,
            course_credits_type: undefined,
          },
          {
            course_id: "PHYS 4305",
            course_name: "Quantum Mechanics",
            course_description:
              "A mathematical treatment of quantized physical phenomena. Topics include the wave theory of matter, the principles of superposition, probability, expectation values, coordinate representation, momentum representation, indeterminacy, Hermitian operators, angular momentum, and spin. Quantum solutions for simple barriers, potential wells, harmonic oscillator, and the hydrogen atom are presented.",
            course_prerequisites: "PHYS 3310 and MATH 3330",
            course_credits_min: undefined,
            course_credits_max: undefined,
            course_credits_type: undefined,
          },
          {
            course_id: "PHYS 4310",
            course_name: "Advanced Modern Physics",
            course_description:
              "Continuation of PHYS 3310. Topics include atomic, molecular, nuclear, statistical, solid state, laser and elementary particle physics.",
            course_prerequisites: "PHYS 3310 and MATH 3330",
            course_credits_min: undefined,
            course_credits_max: undefined,
            course_credits_type: undefined,
          },
          {
            course_id: "PHYS 4315",
            course_name: "Mathematical Methods of Physic",
            course_description:
              "A course presenting mathematical techniques used in physics and engineering. The course will survey, at a brief introductory level and from a physics perspective, numerous mathematical techniques from areas such as infinite series, integral transformation, applications of complex variables, matrices and tensors, special functions, partial differential equations, Green's functions, perturbation theory, integral equations, calculus of variations, and groups and group representations.",
            course_prerequisites: "PHYS 2326/2126 and MATH 3330",
            course_credits_min: undefined,
            course_credits_max: undefined,
            course_credits_type: undefined,
          },
          {
            course_id: "PHYS 4399",
            course_name: "Special Topics in Physics",
            course_description:
              "Selected topics in physics are covered, depending on student interest. Credit will be given more than once if the topic varies.",
            course_prerequisites: "Permission of instructor",
            course_credits_min: undefined,
            course_credits_max: undefined,
            course_credits_type: undefined,
          },
        ]
      );
    });
  });
});
