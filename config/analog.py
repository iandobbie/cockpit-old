aout_keys = ['name', 
             'cockpit_axis', 
             'aline', 
             'sensitivity', 
             'hard_limits', 
             'soft_limits', 
             'deltas', 
             'default_delta',
             'startup_value',]

aouts = [(
            'Z piezo',   # Z jena piezo, V2
            'z',    # move stage in Z
            2,          # on analogue out 2
            6.437,          # microns / V
            (0, 35),
            (0, 35),
            [0.01, 0.05, 0.1, 0.5, 1],
            2,
            17.5
         ),
#         (
#            'z_insert',
#            'z',
#            0,          # on analogue out 0
#            20,         # microns / V
#            (0, 100),
#            (0, 91.13),
#            [.05, .1, .5, 1, 2, 5, 10],
#            2,
#            45,
 #        )  
        ]
